$ErrorActionPreference = 'Stop'
$Project = 'C:\Users\User\Sea-Sentinel-V2'
$SecretFile = Join-Path $Project '.aisstream_key.dpapi'
if (-not (Test-Path $Project)) { throw "Project folder not found: $Project" }
$secret = Read-Host 'Enter a NEW AISStream API key (hidden)' -AsSecureString
if ($secret.Length -eq 0) { throw 'Empty key. Nothing saved.' }
# Export-Clixml uses Windows DPAPI, bound to this Windows user and computer.
$secret | Export-Clixml -LiteralPath $SecretFile
Write-Host "Key saved encrypted for this Windows user at $SecretFile" -ForegroundColor Green
Write-Host 'Do not commit this file to GitHub. Run START_SEA_SENTINEL.ps1 next.'
