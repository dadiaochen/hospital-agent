param(
    [switch]$SkipBuild,
    [switch]$SkipScenarios
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

Push-Location $repoRoot
try {
    docker version | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Docker Desktop is not running or the Docker CLI is unavailable."
    }

    if (-not (Test-Path ".env")) {
        Copy-Item ".env.example" ".env"
        Write-Host "Created .env from .env.example."
    }
    New-Item -ItemType Directory -Force "var\demo" | Out-Null

    $composeArgs = @("compose", "up", "-d", "--wait", "--wait-timeout", "300")
    if (-not $SkipBuild) {
        $composeArgs += "--build"
    }
    & docker @composeArgs
    if ($LASTEXITCODE -ne 0) {
        throw "Docker Compose failed to start a healthy MVP stack."
    }

    if (-not $SkipScenarios) {
        & (Join-Path $PSScriptRoot "run_demo.ps1")
        if ($LASTEXITCODE -ne 0) {
            throw "The fixed four-scenario demo did not pass."
        }
    }

    Write-Host ""
    Write-Host "MVP services are ready:"
    Write-Host "  Frontend: http://localhost:3000"
    Write-Host "  Swagger:  http://localhost:8000/docs"
    Write-Host "  Health:   http://localhost:8000/health"
    Write-Host "Run .\scripts\stop_demo.ps1 to stop containers without deleting data."
}
finally {
    Pop-Location
}
