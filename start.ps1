# Launch Loki (localhost only)
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

if (-not (Test-Path ".\.venv\Scripts\python.exe")) {
    Write-Host "Creating virtual environment..."
    python -m venv .venv
    .\.venv\Scripts\pip install -r requirements.txt
}

if (-not (Test-Path ".\.env")) {
    Write-Host "Copy .env.example to .env and add your GROQ_API_KEY"
}

if (Test-Path ".\.env") {
    Get-Content ".\.env" | ForEach-Object {
        if ($_ -match '^\s*([^#][^=]+)=(.*)$') {
            [System.Environment]::SetEnvironmentVariable($matches[1].Trim(), $matches[2].Trim(), "Process")
        }
    }
}

$port = if ($env:SERVER_PORT) { $env:SERVER_PORT } else { 8787 }

Write-Host "Loki: http://127.0.0.1:$port/ui/"
Start-Process "http://127.0.0.1:$port/ui/"
.\.venv\Scripts\python -m uvicorn backend.main:app --host 127.0.0.1 --port $port
