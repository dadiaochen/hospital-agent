param(
    [string]$BaseUrl = "http://localhost:8000",
    [string]$RunKeyPrefix = "3d-$((Get-Date).ToUniversalTime().ToString('yyyyMMddHHmmss'))"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

Push-Location $repoRoot
try {
    docker compose exec -T backend python -m app.agent.demo_runner `
        --base-url $BaseUrl `
        --run-key-prefix $RunKeyPrefix `
        --json-report /app/var/demo/mvp-demo.json `
        --markdown-report /app/var/demo/mvp-demo.md
    if ($LASTEXITCODE -ne 0) {
        throw "The fixed four-scenario demo failed. Review the output above."
    }
}
finally {
    Pop-Location
}
