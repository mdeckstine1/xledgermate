# Build XLedgerMate-Dashboard.exe (Windows GUI launcher, no terminal needed to start).
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$cs = Join-Path $here "XLedgerMateDashboardLauncher.cs"
$out = Join-Path $here "XLedgerMate-Dashboard.exe"

$csc = @(
    "${env:WINDIR}\Microsoft.NET\Framework64\v4.0.30319\csc.exe",
    "${env:WINDIR}\Microsoft.NET\Framework\v4.0.30319\csc.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1

if (-not $csc) {
    Write-Error "csc.exe not found. Install .NET Framework Developer Pack or use Start-XLedgerMate-Dashboard.bat"
}

$refs = @(
    "/reference:System.Windows.Forms.dll",
    "/reference:System.Drawing.dll"
)

& $csc /nologo /target:winexe /optimize+ /out:$out $refs $cs
Write-Host "Built: $out"
Write-Host "Double-click XLedgerMate-Dashboard.exe to open the monitoring GUI."