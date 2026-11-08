# Wave | BrainVault Mint: update on Windows in one step.
# Run from anywhere:  powershell -ExecutionPolicy Bypass -File "$env:USERPROFILE\wave-os-hermes\brainvault\scripts\update-windows.ps1"
$ErrorActionPreference = "Stop"
$repo = Join-Path $env:USERPROFILE "wave-os-hermes"
$dest = Join-Path $env:LOCALAPPDATA "hermes\plugins\brainvault"

Write-Host "1/4  Getting the latest version..."
git -C $repo pull

Write-Host "2/4  Copying the plugin into Hermes..."
New-Item -ItemType Directory -Force $dest | Out-Null
Copy-Item -Recurse -Force (Join-Path $repo "brainvault\*") $dest
$nested = Join-Path $dest "brainvault"
if (Test-Path $nested) { Remove-Item -Recurse -Force $nested }  # left over from copying the folder instead of its contents

Write-Host "3/4  Stopping Hermes so it loads the new version..."
try { hermes gateway stop 2>$null | Out-Null } catch {}
Get-Process | Where-Object { $_.ProcessName -like "hermes*" } | Stop-Process -Force -ErrorAction SilentlyContinue

Write-Host "4/4  Checking..."
hermes brainvault doctor
Write-Host ""
Write-Host "Done. Open Hermes Desktop again; the page footer should show the version above."
