# Copy dashboard folder to VPS (when groks input is not on GitHub yet).
param(
    [string]$VpsIp = "188.245.50.229",
    [string]$KeyPath = "$env:USERPROFILE\.ssh\hetzner_xledgermate",
    [string]$RepoRoot = "C:\Users\micha\xledgermate"
)

$localDash = Join-Path $RepoRoot "groks input\vps\dashboard"
$remoteDir = "/root/xledgermate/groks input/vps/dashboard"

Write-Host "Uploading dashboard to VPS..."
ssh -i $KeyPath "root@${VpsIp}" "mkdir -p '${remoteDir}'"
scp -i $KeyPath -r (Join-Path $localDash "*") "root@${VpsIp}:${remoteDir}/"

Write-Host "Run install on VPS:"
Write-Host "  ssh -i $KeyPath root@$VpsIp 'bash /root/xledgermate/groks input/vps/dashboard/install_on_vps.sh'"