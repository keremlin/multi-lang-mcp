param(
    [Parameter(Mandatory=$true)]
    [string]$name
)

try {
    # Get service GUIDs from active BTHENUM service nodes (only present when connected)
    $pnpSvc = Get-PnpDevice -ErrorAction SilentlyContinue |
        Where-Object { $_.FriendlyName -like "*$name*" -and $_.InstanceId -match '^BTHENUM\\\{[0-9A-Fa-f\-]+\}' }

    if (-not $pnpSvc) {
        Write-Output (@{
            success = $false
            error   = "Device '$name' does not appear to be currently connected (no active Bluetooth service entries found)"
        } | ConvertTo-Json -Compress)
        exit 1
    }

    # Extract device MAC address from root DEV_ entry
    $rootDev = Get-PnpDevice -ErrorAction SilentlyContinue |
        Where-Object { $_.FriendlyName -like "*$name*" -and $_.InstanceId -match '^BTHENUM\\DEV_[0-9A-Fa-f]{12}' } |
        Select-Object -First 1
    $addrHex = if ($rootDev -and $rootDev.InstanceId -match 'BTHENUM\\DEV_([0-9A-Fa-f]{12})') { $Matches[1] } else { "" }
    $addrFmt = if ($addrHex) { (($addrHex -split '(?<=\G.{2})(?=.)') -join ':').ToUpper() } else { "" }

    # Collect unique service GUIDs
    $guids = [System.Collections.Generic.List[guid]]::new()
    foreach ($svc in $pnpSvc) {
        if ($svc.InstanceId -match 'BTHENUM\\(\{[0-9A-Fa-f\-]+\})_') {
            $g = [guid]$Matches[1]
            if (-not $guids.Contains($g)) { $guids.Add($g) }
        }
    }

    if ($guids.Count -eq 0) {
        Write-Output (@{ success = $false; error = "Could not extract service GUIDs for '$name'" } | ConvertTo-Json -Compress)
        exit 1
    }

    $code = @'
using System;
using System.Runtime.InteropServices;
using System.Collections.Generic;

[StructLayout(LayoutKind.Sequential)]
public struct BtSysTime { public ushort a,b,c,d,e,f,g,h; }

[StructLayout(LayoutKind.Sequential, CharSet=CharSet.Unicode)]
public struct BtDevInfo {
    public uint dwSize; public ulong Address; public uint ulCoD;
    [MarshalAs(UnmanagedType.Bool)] public bool fConnected;
    [MarshalAs(UnmanagedType.Bool)] public bool fRemembered;
    [MarshalAs(UnmanagedType.Bool)] public bool fAuthenticated;
    public BtSysTime stLastSeen; public BtSysTime stLastUsed;
    [MarshalAs(UnmanagedType.ByValTStr, SizeConst=248)] public string szName;
}
[StructLayout(LayoutKind.Sequential, CharSet=CharSet.Unicode)]
public struct BtSearchParams {
    public uint dwSize;
    [MarshalAs(UnmanagedType.Bool)] public bool fAuth;
    [MarshalAs(UnmanagedType.Bool)] public bool fRem;
    [MarshalAs(UnmanagedType.Bool)] public bool fUnk;
    [MarshalAs(UnmanagedType.Bool)] public bool fConn;
    [MarshalAs(UnmanagedType.Bool)] public bool fInq;
    public byte cTmo; public IntPtr hRadio;
}
[StructLayout(LayoutKind.Sequential)]
public struct BtRadioParams { public uint dwSize; }

public static class BtServiceState {
    [DllImport("BluetoothApis.dll",SetLastError=true)] public static extern IntPtr BluetoothFindFirstRadio(ref BtRadioParams p, out IntPtr ph);
    [DllImport("BluetoothApis.dll",SetLastError=true)] public static extern bool BluetoothFindRadioClose(IntPtr h);
    [DllImport("kernel32.dll",SetLastError=true)] public static extern bool CloseHandle(IntPtr h);
    [DllImport("BluetoothApis.dll",SetLastError=true,CharSet=CharSet.Unicode)] public static extern IntPtr BluetoothFindFirstDevice(ref BtSearchParams sp, ref BtDevInfo di);
    [DllImport("BluetoothApis.dll",SetLastError=true,CharSet=CharSet.Unicode)] public static extern bool BluetoothFindNextDevice(IntPtr h, ref BtDevInfo di);
    [DllImport("BluetoothApis.dll",SetLastError=true)] public static extern bool BluetoothFindDeviceClose(IntPtr h);
    [DllImport("BluetoothApis.dll",SetLastError=true)] public static extern uint BluetoothSetServiceState(IntPtr hRadio, ref BtDevInfo di, ref Guid guid, uint flags);

    public static string SetState(ulong addr, Guid[] guids, uint flags) {
        var rfp = new BtRadioParams { dwSize=(uint)Marshal.SizeOf(typeof(BtRadioParams)) };
        IntPtr hRadio=IntPtr.Zero, hFR=BluetoothFindFirstRadio(ref rfp, out hRadio);
        if(hFR!=IntPtr.Zero) BluetoothFindRadioClose(hFR);
        var sp = new BtSearchParams { dwSize=(uint)Marshal.SizeOf(typeof(BtSearchParams)), fAuth=true, fRem=true, fConn=true, hRadio=hRadio };
        uint sz=(uint)Marshal.SizeOf(typeof(BtDevInfo));
        var di=new BtDevInfo{dwSize=sz};
        IntPtr hF=BluetoothFindFirstDevice(ref sp, ref di);
        BtDevInfo? found=null;
        if(hF!=IntPtr.Zero){
            do{ if(di.Address==addr){found=di;break;} di=new BtDevInfo{dwSize=sz}; }
            while(BluetoothFindNextDevice(hF,ref di));
            BluetoothFindDeviceClose(hF);
        }
        if(!found.HasValue){CloseHandle(hRadio);return "ERROR:Device not found in Bluetooth stack";}
        var dev=found.Value;
        int ok=0; var errs=new List<string>();
        foreach(var g in guids){ var gg=g; uint e=BluetoothSetServiceState(hRadio,ref dev,ref gg,flags); if(e==0)ok++; else errs.Add(e.ToString()); }
        CloseHandle(hRadio);
        return ok>0?"OK:"+ok:(errs.Count>0?"ERROR:SetServiceState errors: "+string.Join(",",errs):"ERROR:No services changed");
    }
}
'@
    Add-Type -TypeDefinition $code -Language CSharp -ErrorAction Stop

    $addrUlong = [Convert]::ToUInt64($addrHex, 16)
    $result = [BtServiceState]::SetState($addrUlong, $guids.ToArray(), 0)  # 0 = DISABLE

    if ($result.StartsWith("ERROR:")) {
        Write-Output (@{ success = $false; error = $result.Substring(6) } | ConvertTo-Json -Compress)
        exit 1
    }

    Write-Output (@{
        success = $true
        data    = @{ name = $name; address = $addrFmt; message = "Disconnected '$name' successfully" }
    } | ConvertTo-Json -Compress)

} catch {
    Write-Output (@{ success = $false; error = $_.Exception.Message } | ConvertTo-Json -Compress)
    exit 1
}
