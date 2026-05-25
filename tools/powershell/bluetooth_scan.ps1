param(
    [int]$timeout_seconds = 10  # kept for API compatibility
)

try {
    # Load WinRT for accurate ConnectionStatus (matches Windows Settings)
    Add-Type -AssemblyName System.Runtime.WindowsRuntime
    $null = [Windows.Devices.Bluetooth.BluetoothDevice,Windows.Devices.Bluetooth,ContentType=WindowsRuntime]
    $null = [Windows.Devices.Bluetooth.BluetoothConnectionStatus,Windows.Devices.Bluetooth,ContentType=WindowsRuntime]

    $asTaskM = [System.WindowsRuntimeSystemExtensions].GetMethods() |
        Where-Object { $_.Name -eq 'AsTask' -and $_.IsGenericMethod -and $_.GetParameters().Count -eq 1 -and
                       $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' } |
        Select-Object -First 1

    function Await {
        param($AsyncOp, [Type]$ResultType, [int]$TimeoutMs = 5000)
        $task = $asTaskM.MakeGenericMethod($ResultType).Invoke($null, @($AsyncOp))
        $null = $task.Wait($TimeoutMs)
        if ($task.IsFaulted) { return $null }
        if (-not $task.IsCompleted) { return $null }
        return $task.Result
    }

    # Enumerate paired devices from PnP (fast, no radio scan)
    $pnpDevices = Get-PnpDevice -ErrorAction SilentlyContinue |
        Where-Object { $_.InstanceId -match '^BTHENUM\\DEV_[0-9A-Fa-f]{12}' }

    $results = [System.Collections.Generic.List[object]]::new()
    $seen    = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::OrdinalIgnoreCase)

    foreach ($dev in $pnpDevices) {
        $name = $dev.FriendlyName
        if (-not $name) { continue }

        $addrHex = if ($dev.InstanceId -match 'BTHENUM\\DEV_([0-9A-Fa-f]{12})') { $Matches[1] } else { "" }
        $addrFmt = if ($addrHex) { (($addrHex -split '(?<=\G.{2})(?=.)') -join ':').ToUpper() } else { "" }

        $key = if ($addrFmt) { $addrFmt } else { $name }
        if (-not $seen.Add($key)) { continue }

        # Check actual connection status via WinRT (same source as Windows Settings)
        $connected = $false
        if ($addrHex) {
            $addrUlong = [Convert]::ToUInt64($addrHex, 16)
            $btDev = Await ([Windows.Devices.Bluetooth.BluetoothDevice]::FromBluetoothAddressAsync($addrUlong)) `
                           ([Windows.Devices.Bluetooth.BluetoothDevice])
            if ($btDev) {
                $connected = ($btDev.ConnectionStatus -eq [Windows.Devices.Bluetooth.BluetoothConnectionStatus]::Connected)
            }
        }

        $results.Add(@{
            name      = $name
            address   = $addrFmt
            connected = $connected
            paired    = $true
            signal    = $null
        })
    }

    Write-Output (@{
        success = $true
        data    = @{ count = $results.Count; devices = @($results) }
    } | ConvertTo-Json -Depth 5 -Compress)

} catch {
    Write-Output (@{ success = $false; error = $_.Exception.Message } | ConvertTo-Json -Compress)
    exit 1
}
