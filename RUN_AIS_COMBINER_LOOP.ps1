$Project = 'C:\Users\User\Sea-Sentinel-V2'
$Python = 'C:\Users\User\anaconda3\envs\sea-sentinel-v2\python.exe'
$Combiner = Join-Path $Project 'ais_tracking\ais_combiner_malaysia_coverage.py'
Set-Location $Project
while ($true) {
  try { & $Python $Combiner }
  catch { Write-Warning "AIS combiner error: $_" }
  Start-Sleep -Seconds 30
}
