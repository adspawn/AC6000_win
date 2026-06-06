# Stop other bind_init.py processes (Windows BLE GATT conflict prevention).
$ErrorActionPreference = "SilentlyContinue"
$stale = @(Get-CimInstance Win32_Process | Where-Object {
        $_.CommandLine -and $_.CommandLine -match 'bind_init\.py'
    })

if ($stale.Count -eq 0) {
    Write-Host "  No stale bind_init.py found."
    exit 0
}

Write-Host "  Found $($stale.Count) stale bind_init.py process(es)."
foreach ($p in $stale) {
    Write-Host "  Stopping PID $($p.ProcessId) ..."
    Stop-Process -Id $p.ProcessId -Force
}
Write-Host "  Waiting 3s for BLE/GATT release..."
Start-Sleep -Seconds 3
exit 0
