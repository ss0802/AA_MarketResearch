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

$startedAt = Get-Date -Format "yyyy-MM-dd HH:mm:ss K"
"[$startedAt] Starting $Market Tradeable EOD ingestion" | Out-File -FilePath $logPath -Append -Encoding utf8

& $pythonPath manage.py ingest_tradeable --mode eod --market $Market *>> $logPath
$ingestionExitCode = $LASTEXITCODE

if ($ingestionExitCode -eq 0) {
    "[$(Get-Date -Format "yyyy-MM-dd HH:mm:ss K")] Computing $Market technical snapshots" | Out-File -FilePath $logPath -Append -Encoding utf8
    & $pythonPath manage.py compute_technicals --market $Market *>> $logPath
    $exitCode = $LASTEXITCODE
}
else {
    $exitCode = $ingestionExitCode
    "[$(Get-Date -Format "yyyy-MM-dd HH:mm:ss K")] Skipped technicals because EOD ingestion failed" | Out-File -FilePath $logPath -Append -Encoding utf8
}

$finishedAt = Get-Date -Format "yyyy-MM-dd HH:mm:ss K"
"[$finishedAt] Finished with exit code $exitCode" | Out-File -FilePath $logPath -Append -Encoding utf8
exit $exitCode
