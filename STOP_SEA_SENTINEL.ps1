$Project = 'C:\Users\User\Sea-Sentinel-V2'
$PidFile = Join-Path $Project '.sea_sentinel_launcher_pids.json'
if (-not (Test-Path $PidFile)) { Write-Warning 'No launcher PID file found.'; return }
$ids = Get-Content -LiteralPath $PidFile -Raw | ConvertFrom-Json
foreach ($name in @('receiver','combiner','streamlit')) {
  $processId = $ids.$name
  if ($processId) {
    $p = Get-Process -Id $processId -ErrorAction SilentlyContinue
    if ($p -and ($p.ProcessName -match 'python|powershell')) {
      Stop-Process -Id $processId -ErrorAction SilentlyContinue
      Write-Host "Stopped $name PID $processId"
    }
  }
}
Remove-Item -LiteralPath $PidFile -Force
