param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("IND", "US")]
    [string]$Market
)

$ErrorActionPreference = "Stop"

$projectPath = "D:\AA_MarketResearch"
$pythonPath = Join-Path $projectPath ".venv\Scripts\python.exe"
$logDirectory = Join-Path $projectPath "logs"
$logPath = Join-Path $logDirectory ("eod-" + $Market.ToLower() + "-" + (Get-Date -Format "yyyy-MM-dd") + ".log")

New-Item -ItemType Directory -Path $logDirectory -Force | Out-Null
Set-Location -LiteralPath $projectPath

$now = Get-Date
if ($Market -eq "IND" -and $now.TimeOfDay -lt [TimeSpan]::FromHours(17.75)) {
    "[$($now.ToString('yyyy-MM-dd HH:mm:ss K'))] Skipped IND EOD: market-close guard requires 17:45 IST or later" | Out-File -FilePath $logPath -Append -Encoding utf8
    exit 0
}
if ($Market -eq "US" -and $now.TimeOfDay -lt [TimeSpan]::FromHours(5.5)) {
    "[$($now.ToString('yyyy-MM-dd HH:mm:ss K'))] Skipped US EOD: completion guard requires 05:30 IST or later" | Out-File -FilePath $logPath -Append -Encoding utf8
    exit 0
}

$mutex = [System.Threading.Mutex]::new($false, "Local\AA_MarketResearch_EOD")
$hasMutex = $false
try {
    try {
        $hasMutex = $mutex.WaitOne(0)
    }
    catch [System.Threading.AbandonedMutexException] {
        $hasMutex = $true
    }
    if (-not $hasMutex) {
        "[$($now.ToString('yyyy-MM-dd HH:mm:ss K'))] Skipped $Market EOD: another market ingestion is already running" | Out-File -FilePath $logPath -Append -Encoding utf8
        exit 0
    }

$startedAt = Get-Date -Format "yyyy-MM-dd HH:mm:ss K"
$exitCode = 0
"[$startedAt] Starting $Market Tradeable EOD ingestion" | Out-File -FilePath $logPath -Append -Encoding utf8

$ErrorActionPreference = "Continue"
& $pythonPath -u manage.py ingest_tradeable --mode eod --market $Market --retries 2 --retry-wait 2 2>&1 |
    ForEach-Object {
        $_ | Out-File -FilePath $logPath -Append -Encoding utf8
    }
$ingestionExitCode = $LASTEXITCODE
$ErrorActionPreference = "Stop"

if ($ingestionExitCode -eq 0) {
    "[$(Get-Date -Format "yyyy-MM-dd HH:mm:ss K")] Refreshing $Market regime benchmark" | Out-File -FilePath $logPath -Append -Encoding utf8
    $ErrorActionPreference = "Continue"
    & $pythonPath -u manage.py ingest_regime_benchmark --market $Market 2>&1 |
        ForEach-Object {
            $_ | Out-File -FilePath $logPath -Append -Encoding utf8
        }
    $benchmarkExitCode = $LASTEXITCODE
    $ErrorActionPreference = "Stop"
    if ($benchmarkExitCode -ne 0) {
        $exitCode = $benchmarkExitCode
    }
    "[$(Get-Date -Format "yyyy-MM-dd HH:mm:ss K")] Computing $Market technical snapshots" | Out-File -FilePath $logPath -Append -Encoding utf8
    $ErrorActionPreference = "Continue"
    & $pythonPath -u manage.py compute_technicals --market $Market 2>&1 |
        ForEach-Object {
            $_ | Out-File -FilePath $logPath -Append -Encoding utf8
        }
    $technicalExitCode = $LASTEXITCODE
    if ($technicalExitCode -ne 0) { $exitCode = $technicalExitCode }
    $ErrorActionPreference = "Stop"
    if ($exitCode -eq 0) {
        "[$(Get-Date -Format "yyyy-MM-dd HH:mm:ss K")] Computing $Market market regime" | Out-File -FilePath $logPath -Append -Encoding utf8
        $ErrorActionPreference = "Continue"
        & $pythonPath -u manage.py compute_market_regime --market $Market 2>&1 |
            ForEach-Object {
                $_ | Out-File -FilePath $logPath -Append -Encoding utf8
            }
        $exitCode = $LASTEXITCODE
        $ErrorActionPreference = "Stop"
    }
}
else {
    $exitCode = $ingestionExitCode
    "[$(Get-Date -Format "yyyy-MM-dd HH:mm:ss K")] Skipped technicals because EOD ingestion failed" | Out-File -FilePath $logPath -Append -Encoding utf8
}

$finishedAt = Get-Date -Format "yyyy-MM-dd HH:mm:ss K"
"[$finishedAt] Finished with exit code $exitCode" | Out-File -FilePath $logPath -Append -Encoding utf8
}
finally {
    if ($hasMutex) {
        $mutex.ReleaseMutex()
    }
    $mutex.Dispose()
}
exit $exitCode
