$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$cs = Join-Path $here "XLedgerMateFullGuiLauncher.cs"
$out = Join-Path $here "XLedgerMate-Full-GUI.exe"

$csc = @(
    "${env:WINDIR}\Microsoft.NET\Framework64\v4.0.30319\csc.exe",
    "${env:WINDIR}\Microsoft.NET\Framework\v4.0.30319\csc.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1

if (-not $csc) { Write-Error "csc.exe not found" }

& $csc /nologo /target:winexe /optimize+ /out:$out `
  /reference:System.Windows.Forms.dll `
  /reference:System.Drawing.dll `
  $cs

Copy-Item $out (Join-Path (Split-Path $here -Parent) "XLedgerMate-Full-GUI.exe") -Force
Write-Host "Built: $out"