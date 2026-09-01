# Fluid Q US - daily refresh
# Re-pulls S&P 500 + Nasdaq 100 data and rebuilds dist\index.html.
# Safe to run any time; it always uses the latest completed US session.

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

$logDir = Join-Path $root "logs"
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir | Out-Null }
$log = Join-Path $logDir ("refresh-" + (Get-Date -Format "yyyy-MM-dd") + ".log")

"=== $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss zzz') ===" | Tee-Object -FilePath $log -Append

try {
    python build.py 2>&1 | Tee-Object -FilePath $log -Append
    if ($LASTEXITCODE -ne 0) { throw "build.py exited $LASTEXITCODE" }
    "OK  -> $(Join-Path $root 'dist\index.html')" | Tee-Object -FilePath $log -Append
}
catch {
    "FAILED: $_" | Tee-Object -FilePath $log -Append
    exit 1
}

# Keep a month of logs, drop the rest.
Get-ChildItem $logDir -Filter "refresh-*.log" |
    Sort-Object LastWriteTime -Descending |
    Select-Object -Skip 31 |
    Remove-Item -Force -ErrorAction SilentlyContinue
