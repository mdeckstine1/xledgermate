# SSH tunnel from Windows to VPS Streamlit dashboard (localhost:8501).
# Usage:
#   .\start_tunnel.ps1
#   .\start_tunnel.ps1 -VpsIp 188.245.50.229

param(
    [string]$VpsIp = "188.245.50.229",
    [string]$KeyPath = "$env:USERPROFILE\.ssh\hetzner_xledgermate",
    [int]$LocalPort = 8501
)

Write-Host "Tunnel: http://localhost:$LocalPort -> ${VpsIp}:8501"
Write-Host "Keep this window open. Ctrl+C to close."
Write-Host ""

ssh -i $KeyPath -N -L "${LocalPort}:127.0.0.1:8501" "root@${VpsIp}"