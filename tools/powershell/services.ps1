param(
    [string]$FilterName = ""
)

try {
    if ($FilterName -ne "") {
        $services = Get-Service -Name "*$FilterName*" -ErrorAction SilentlyContinue
    } else {
        $services = Get-Service -ErrorAction SilentlyContinue
    }

    $data = $services | Select-Object Name, DisplayName, Status | ForEach-Object {
        @{
            name        = $_.Name
            displayName = $_.DisplayName
            status      = $_.Status.ToString()
        }
    }

    $output = @{
        success = $true
        data    = @{ services = @($data) }
    }
    Write-Output ($output | ConvertTo-Json -Depth 5 -Compress)
} catch {
    $err = @{ success = $false; error = $_.Exception.Message }
    Write-Output ($err | ConvertTo-Json -Compress)
    exit 1
}
