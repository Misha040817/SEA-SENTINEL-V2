$ErrorActionPreference = 'Stop'
$Project = 'C:\Users\User\Sea-Sentinel-V2'
$Python = 'C:\Users\User\anaconda3\envs\sea-sentinel-v2\python.exe'
$SecretFile = Join-Path $Project '.aisstream_key.dpapi'
$Dashboard = 'SEA_SENTINEL_V2_DROPDOWN_FIXED.py'
if (-not (Test-Path $Python)) { throw "Python not found: $Python" }
if (-not (Test-Path (Join-Path $Project $Dashboard))) { throw 'Dashboard file not found.' }
if (-not (Test-Path $SecretFile)) { throw 'Encrypted API key missing. Run SETUP_AIS_KEY.ps1 first.' }
# Decrypt key only in this user session. Do not print it or pass it on a command line.
$secure = Import-Clixml -LiteralPath $SecretFile
$bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
try { $env:AISSTREAM_API_KEY = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr) }
finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) }
if ([string]::IsNullOrWhiteSpace($env:AISSTREAM_API_KEY)) { throw 'AISStream key is empty.' }
$env:PYTHONUNBUFFERED = '1'
$receiver = Join-Path $Project 'ais_tracking\ais_client_malaysia_all_regions.py'
$combiner = Join-Path $Project 'ais_tracking\ais_combiner_malaysia_coverage.py'
if (-not (Test-Path $receiver) -or -not (Test-Path $combiner)) { throw 'AIS receiver or combiner file missing.' }
Write-Host 'Starting AIS receiver...' -ForegroundColor Cyan
$rx = Start-Process -FilePath $Python -ArgumentList @($receiver) -WorkingDirectory $Project -PassThru
Write-Host "AIS receiver PID: $($rx.Id)"
Write-Host 'Starting combiner loop (every 30 seconds)...' -ForegroundColor Cyan
$combinerLoop = Join-Path $PSScriptRoot 'RUN_AIS_COMBINER_LOOP.ps1'
# Separate PowerShell process runs the combiner repeatedly. It needs no API key.
$cb = Start-Process -FilePath 'powershell.exe' -ArgumentList @('-NoProfile','-ExecutionPolicy','Bypass','-File',('"'+$combinerLoop+'"')) -WorkingDirectory $Project -PassThru
Write-Host "Combiner loop PID: $($cb.Id)"
Write-Host 'Starting dashboard at http://localhost:8576 ...' -ForegroundColor Cyan
$st = Start-Process -FilePath $Python -ArgumentList @('-m','streamlit','run',$Dashboard,'--server.port','8576','--server.headless','true') -WorkingDirectory $Project -PassThru
Write-Host "Streamlit PID: $($st.Id)"
Start-Sleep -Seconds 5
Start-Process 'http://localhost:8576'
Write-Host 'Started. Keep this PowerShell window open for status. AIS receiver and combiner run separately.' -ForegroundColor Green
Write-Host 'To stop, run STOP_SEA_SENTINEL.ps1 (only processes recorded by this launcher).' -ForegroundColor Yellow
@{receiver=$rx.Id;combiner=$cb.Id;streamlit=$st.Id} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $Project '.sea_sentinel_launcher_pids.json') -Encoding UTF8
Remove-Item Env:AISSTREAM_API_KEY -ErrorAction SilentlyContinue




