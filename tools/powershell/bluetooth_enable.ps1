param(
    [Parameter(Mandatory=$true)]
    [ValidateSet("enable","disable")]
    [string]$state
)

try {
    Add-Type -AssemblyName System.Runtime.WindowsRuntime

    $asTaskMethod = [System.WindowsRuntimeSystemExtensions].GetMethods() |
        Where-Object { $_.Name -eq 'AsTask' -and $_.IsGenericMethod -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' } |
        Select-Object -First 1

    function Await {
        param($AsyncOp, [Type]$ResultType)
        $task = $asTaskMethod.MakeGenericMethod($ResultType).Invoke($null, @($AsyncOp))
        $null = $task.Wait(30000)
        return $task.Result
    }

    $null = [Windows.Devices.Radios.Radio,Windows.Devices.Radios,ContentType=WindowsRuntime]
    $null = [Windows.Devices.Radios.RadioKind,Windows.Devices.Radios,ContentType=WindowsRuntime]
    $null = [Windows.Devices.Radios.RadioState,Windows.Devices.Radios,ContentType=WindowsRuntime]
    $null = [Windows.Devices.Radios.RadioAccessStatus,Windows.Devices.Radios,ContentType=WindowsRuntime]

    $radios = Await ([Windows.Devices.Radios.Radio]::GetRadiosAsync()) `
              ([System.Collections.Generic.IReadOnlyList[Windows.Devices.Radios.Radio]])

    $btRadio = $radios | Where-Object { $_.Kind -eq [Windows.Devices.Radios.RadioKind]::Bluetooth } | Select-Object -First 1

    if (-not $btRadio) {
        Write-Output (@{ success = $false; error = "No Bluetooth radio found on this system" } | ConvertTo-Json -Compress)
        exit 1
    }

    $targetState = if ($state -eq "enable") { [Windows.Devices.Radios.RadioState]::On } else { [Windows.Devices.Radios.RadioState]::Off }
    $accessStatus = Await ($btRadio.SetStateAsync($targetState)) ([Windows.Devices.Radios.RadioAccessStatus])

    if ($accessStatus -eq [Windows.Devices.Radios.RadioAccessStatus]::Allowed) {
        Write-Output (@{
            success = $true
            data    = @{ state = $state; message = "Bluetooth ${state}d successfully" }
        } | ConvertTo-Json -Compress)
    } else {
        Write-Output (@{ success = $false; error = "Cannot change Bluetooth state: $accessStatus" } | ConvertTo-Json -Compress)
        exit 1
    }
} catch {
    Write-Output (@{ success = $false; error = $_.Exception.Message } | ConvertTo-Json -Compress)
    exit 1
}
