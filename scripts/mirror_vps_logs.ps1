# Pull /root/xledgermate/logs from VPS into local repo logs/ (gitignored).
# Usage: .\scripts\mirror_vps_logs.ps1

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$LogDir = Join-Path $RepoRoot "logs"
$Key = Join-Path $env:USERPROFILE ".ssh\hetzner_xledgermate"
$Remote = "root@188.245.50.229:/root/xledgermate/logs/."

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
Write-Host "Mirroring VPS logs -> $LogDir"
scp -i $Key -r $Remote $LogDir
Write-Host "Done. Key files: xledgermate.log, runtime_state.json, decisions.jsonl"
