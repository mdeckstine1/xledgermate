# Live XLedgerMate monitor — prints cycle summaries from log + runtime_state
$Root = Split-Path -Parent $PSScriptRoot
if (-not (Test-Path "$Root\logs\xledgermate.log")) { $Root = "c:\Users\micha\xledgermate" }
$Log = Join-Path $Root "logs\xledgermate.log"
$State = Join-Path $Root "logs\runtime_state.json"
$lastLine = 0
if (Test-Path $Log) { $lastLine = (Get-Content $Log | Measure-Object -Line).Lines }

Write-Host "=== XLedgerMate LIVE monitor ===" -ForegroundColor Cyan
Write-Host "Log: $Log"
Write-Host "Ctrl+C to stop`n"

function Show-Snapshot {
    if (-not (Test-Path $State)) { return }
    try {
        $rt = Get-Content $State -Raw | ConvertFrom-Json
        $xrp = [double]$rt.balance_xrp
        $rlusd = [double]$rt.balance_rlusd
        $mid = [double]$rt.mid_price
        $total = $xrp + ($rlusd / $mid)
        $xrpPct = if ($total -gt 0) { 100 * $xrp / $total } else { 0 }
        $spread = if ($rt.spread_validation_ok) { "OK" } else { "FAIL" }
        $kill = if ($rt.kill_switch_active) { "KILL ON" } else { "off" }
        Write-Host (
            "  portfolio={0:N2} XRP | XRP={1:N1} RLUSD={2:N2} ({3:N0}% XRP) | cycle={4} | " +
            "dd={5:N2}% | spread={6} | kill={7} | offers={8}" -f
            $rt.portfolio_value_xrp, $xrp, $rlusd, $xrpPct,
            $rt.cycle_count, 100 * [double]$rt.drawdown_pct, $spread, $kill, $rt.open_offers_count
        ) -ForegroundColor DarkGray
    } catch { }
}

Show-Snapshot

while ($true) {
    if (Test-Path $Log) {
        $lines = Get-Content $Log
        if ($lines.Count -gt $lastLine) {
            $new = $lines[$lastLine..($lines.Count - 1)]
            $lastLine = $lines.Count
            foreach ($line in $new) {
                if ($line -match 'Cycle complete \| (.+)') {
                    $msg = $Matches[1]
                    $color = "Green"
                    if ($msg -match 'spread_check=FAIL') { $color = "Red" }
                    elseif ($msg -match 'placed=0') { $color = "Yellow" }
                    Write-Host "$(Get-Date -Format 'HH:mm:ss') CYCLE $msg" -ForegroundColor $color
                    Show-Snapshot
                }
                elseif ($line -match 'Placed (bid|ask) L1') {
                    Write-Host "$(Get-Date -Format 'HH:mm:ss')   $($line.Substring($line.IndexOf('Placed')))" -ForegroundColor Cyan
                }
                elseif ($line -match 'kill_switch|Kill switch|ERROR|CRITICAL|spread check failed|Live orders blocked') {
                    Write-Host "$(Get-Date -Format 'HH:mm:ss') *** $line" -ForegroundColor Red
                }
            }
        }
    }
    Start-Sleep -Seconds 8
}
