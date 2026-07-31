Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

Push-Location $repoRoot
try {
    docker compose down
    if ($LASTEXITCODE -ne 0) {
        throw "Docker Compose failed to stop the MVP stack."
    }
    Write-Host "MVP containers stopped. PostgreSQL and Redis volumes were preserved."
}
finally {
    Pop-Location
}
