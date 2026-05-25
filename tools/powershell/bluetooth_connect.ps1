param(
    [Parameter(Mandatory=$true)]
    [string]$name
)

try {
    # Load WinRT for accurate connection status checks
    Add-Type -AssemblyName System.Runtime.WindowsRuntime
    $null = [Windows.Devices.Bluetooth.BluetoothDevice,Windows.Devices.Bluetooth,ContentType=WindowsRuntime]
    $null = [Windows.Devices.Bluetooth.BluetoothConnectionStatus,Windows.Devices.Bluetooth,ContentType=WindowsRuntime]

    $asTaskM = [System.WindowsRuntimeSystemExtensions].GetMethods() |
        Where-Object { $_.Name -eq 'AsTask' -and $_.IsGenericMethod -and $_.GetParameters().Count -eq 1 -and
                       $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' } |
        Select-Object -First 1

    function Get-BtConnected([string]$addrHex) {
        $addrUlong = [Convert]::ToUInt64($addrHex, 16)
        $task = $asTaskM.MakeGenericMethod([Windows.Devices.Bluetooth.BluetoothDevice]).Invoke(
            $null, @([Windows.Devices.Bluetooth.BluetoothDevice]::FromBluetoothAddressAsync($addrUlong)))
        $null = $task.Wait(4000)
        if (-not $task.IsCompleted -or $task.IsFaulted) { return $false }
        $dev = $task.Result
        return $dev -and ($dev.ConnectionStatus -eq [Windows.Devices.Bluetooth.BluetoothConnectionStatus]::Connected)
    }

    # Find root paired device node for MAC address
    $rootDev = Get-PnpDevice -ErrorAction SilentlyContinue |
        Where-Object { $_.FriendlyName -like "*$name*" -and $_.InstanceId -match '^BTHENUM\\DEV_[0-9A-Fa-f]{12}' } |
        Select-Object -First 1

    if (-not $rootDev) {
        Write-Output (@{ success = $false; error = "No paired Bluetooth device found matching '$name'" } | ConvertTo-Json -Compress)
        exit 1
    }

    $devName = $rootDev.FriendlyName
    $addrHex = if ($rootDev.InstanceId -match 'BTHENUM\\DEV_([0-9A-Fa-f]{12})') { $Matches[1] } else { "" }
    $addrFmt = if ($addrHex) { (($addrHex -split '(?<=\G.{2})(?=.)') -join ':').ToUpper() } else { "" }

    # Already connected — nothing to do
    if ($addrHex -and (Get-BtConnected $addrHex)) {
        Write-Output (@{
            success = $true
            data    = @{ name = $devName; address = $addrFmt; connected = $true; message = "'$devName' is already connected." }
        } | ConvertTo-Json -Compress)
        exit 0
    }

    $code = @'
using System;
using System.Runtime.InteropServices;
using System.Collections.Generic;

[StructLayout(LayoutKind.Sequential)]
public struct BtSysTime2 { public ushort a,b,c,d,e,f,g,h; }

[StructLayout(LayoutKind.Sequential, CharSet=CharSet.Unicode)]
public struct BtDevInfo2 {
    public uint dwSize; public ulong Address; public uint ulCoD;
    [MarshalAs(UnmanagedType.Bool)] public bool fConnected;
    [MarshalAs(UnmanagedType.Bool)] public bool fRemembered;
    [MarshalAs(UnmanagedType.Bool)] public bool fAuthenticated;
    public BtSysTime2 stLastSeen; public BtSysTime2 stLastUsed;
    [MarshalAs(UnmanagedType.ByValTStr, SizeConst=248)] public string szName;
}
[StructLayout(LayoutKind.Sequential, CharSet=CharSet.Unicode)]
public struct BtSearchParams2 {
    public uint dwSize;
    [MarshalAs(UnmanagedType.Bool)] public bool fAuth;
    [MarshalAs(UnmanagedType.Bool)] public bool fRem;
    [MarshalAs(UnmanagedType.Bool)] public bool fUnk;
    [MarshalAs(UnmanagedType.Bool)] public bool fConn;
    [MarshalAs(UnmanagedType.Bool)] public bool fInq;
    public byte cTmo; public IntPtr hRadio;
}
[StructLayout(LayoutKind.Sequential)]
public struct BtRadioParams2 { public uint dwSize; }

public static class BtServiceState2 {
    [DllImport("BluetoothApis.dll",SetLastError=true)] public static extern IntPtr BluetoothFindFirstRadio(ref BtRadioParams2 p, out IntPtr ph);
    [DllImport("BluetoothApis.dll",SetLastError=true)] public static extern bool BluetoothFindRadioClose(IntPtr h);
    [DllImport("kernel32.dll",SetLastError=true)] public static extern bool CloseHandle(IntPtr h);
    [DllImport("BluetoothApis.dll",SetLastError=true,CharSet=CharSet.Unicode)] public static extern IntPtr BluetoothFindFirstDevice(ref BtSearchParams2 sp, ref BtDevInfo2 di);
    [DllImport("BluetoothApis.dll",SetLastError=true,CharSet=CharSet.Unicode)] public static extern bool BluetoothFindNextDevice(IntPtr h, ref BtDevInfo2 di);
    [DllImport("BluetoothApis.dll",SetLastError=true)] public static extern bool BluetoothFindDeviceClose(IntPtr h);
    [DllImport("BluetoothApis.dll",SetLastError=true)] public static extern uint BluetoothSetServiceState(IntPtr hRadio, ref BtDevInfo2 di, ref Guid guid, uint flags);

    public static string SetState(ulong addr, Guid[] guids, uint flags) {
        var rfp = new BtRadioParams2 { dwSize=(uint)Marshal.SizeOf(typeof(BtRadioParams2)) };
        IntPtr hRadio=IntPtr.Zero, hFR=BluetoothFindFirstRadio(ref rfp, out hRadio);
        if(hFR!=IntPtr.Zero) BluetoothFindRadioClose(hFR);
        var sp = new BtSearchParams2 { dwSize=(uint)Marshal.SizeOf(typeof(BtSearchParams2)), fAuth=true, fRem=true, fConn=true, hRadio=hRadio };
        uint sz=(uint)Marshal.SizeOf(typeof(BtDevInfo2));
        var di=new BtDevInfo2{dwSize=sz};
        IntPtr hF=BluetoothFindFirstDevice(ref sp, ref di);
        BtDevInfo2? found=null;
        if(hF!=IntPtr.Zero){
            do{ if(di.Address==addr){found=di;break;} di=new BtDevInfo2{dwSize=sz}; }
            while(BluetoothFindNextDevice(hF,ref di));
            BluetoothFindDeviceClose(hF);
        }
        if(!found.HasValue){CloseHandle(hRadio);return "ERROR:Device not found in Bluetooth stack";}
        var dev=found.Value;
        int ok=0; var errs=new List<string>();
        foreach(var g in guids){ var gg=g; uint e=BluetoothSetServiceState(hRadio,ref dev,ref gg,flags); if(e==0)ok++; else errs.Add(e.ToString()); }
        CloseHandle(hRadio);
        return ok>0?"OK:"+ok:(errs.Count>0?"ERROR:"+string.Join(",",errs):"ERROR:No services changed");
    }
}
'@
    Add-Type -TypeDefinition $code -Language CSharp -ErrorAction Stop

    # Common Bluetooth Classic profile GUIDs to enable (device will only respond to profiles it supports)
    $guids = @(
        [guid]"{0000110b-0000-1000-8000-00805f9b34fb}",  # A2DP Sink
        [guid]"{0000110d-0000-1000-8000-00805f9b34fb}",  # A2DP Source
        [guid]"{0000111e-0000-1000-8000-00805f9b34fb}",  # HFP Hands-Free AG
        [guid]"{0000111f-0000-1000-8000-00805f9b34fb}",  # HFP Hands-Free
        [guid]"{0000110c-0000-1000-8000-00805f9b34fb}",  # AVRC Controller
        [guid]"{0000110e-0000-1000-8000-00805f9b34fb}",  # AVRC Target
        [guid]"{00001124-0000-1000-8000-00805f9b34fb}",  # HID
        [guid]"{00001108-0000-1000-8000-00805f9b34fb}"   # Headset
    )

    $addrUlong = [Convert]::ToUInt64($addrHex, 16)
    $null = [BtServiceState2]::SetState($addrUlong, $guids, 1)  # 1 = ENABLE

    # Poll for connection (up to 8 seconds regardless of SetState result)
    $connected = $false
    for ($i = 0; $i -lt 16; $i++) {
        Start-Sleep -Milliseconds 500
        if (Get-BtConnected $addrHex) { $connected = $true; break }
    }

    Write-Output (@{
        success = $true
        data    = @{
            name      = $devName
            address   = $addrFmt
            connected = $connected
            message   = if ($connected) { "Connected to '$devName'." } else { "Connect request sent to '$devName'. Device may connect shortly - check Windows Bluetooth settings." }
        }
    } | ConvertTo-Json -Compress)

} catch {
    Write-Output (@{ success = $false; error = $_.Exception.Message } | ConvertTo-Json -Compress)
    exit 1
}
