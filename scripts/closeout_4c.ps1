[CmdletBinding()]
param(
    [switch]$SkipBuild
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$reportRoot = Join-Path $repoRoot "var\closeout"
$jsonReportPath = Join-Path $reportRoot "4c-closeout.json"
$markdownReportPath = Join-Path $reportRoot "4c-closeout.md"
$pythonPath = Join-Path $repoRoot ".venv\Scripts\python.exe"
$steps = [System.Collections.Generic.List[object]]::new()
$startedAt = (Get-Date).ToUniversalTime()
$closeoutStatus = "FAIL"
$failureMessage = $null

function Add-Step {
    param(
        [string]$Name,
        [ValidateSet("PASS", "FAIL")]
        [string]$Status,
        [string]$Evidence
    )

    $steps.Add([pscustomobject]@{
        name = $Name
        status = $Status
        evidence = $Evidence
    }) | Out-Null
}

function Assert-LastExitCode {
    param([string]$Name)

    if ($LASTEXITCODE -ne 0) {
        throw "$Name failed with exit code $LASTEXITCODE."
    }
}

function Write-CloseoutReports {
    param(
        [string]$Status,
        [string]$Failure
    )

    $finishedAt = (Get-Date).ToUniversalTime()
    $report = [pscustomobject]@{
        report_kind = "4c_mvp_closeout"
        status = $Status
        environment = "local_docker_postgresql_redis_deterministic"
        started_at = $startedAt.ToString("o")
        finished_at = $finishedAt.ToString("o")
        steps = @($steps)
        failure = $Failure
    }

    New-Item -ItemType Directory -Force -Path $reportRoot | Out-Null
    $report | ConvertTo-Json -Depth 6 | Set-Content -Encoding UTF8 $jsonReportPath

    $lines = @(
        "# 4C-4 MVP Closeout Run",
        "",
        "> This is a local deterministic Docker acceptance run. It is not a production, clinical, or real-LLM quality claim.",
        "",
        "- Status: ``$Status``",
        "- Environment: ``local_docker_postgresql_redis_deterministic``",
        "- Started at: ``$($startedAt.ToString('o'))``",
        "- Finished at: ``$($finishedAt.ToString('o'))``",
        "",
        "| Step | Status | Evidence |",
        "| --- | --- | --- |"
    )
    foreach ($step in $steps) {
        $lines += "| $($step.name) | $($step.status) | $($step.evidence) |"
    }
    if ($Failure) {
        $lines += ""
        $lines += "Failure: ``$Failure``"
    }
    ($lines -join "`n") | Set-Content -Encoding UTF8 $markdownReportPath
}

Push-Location $repoRoot
try {
    if (-not (Test-Path $pythonPath)) {
        throw "Python virtual environment not found at $pythonPath."
    }
    if (-not (Test-Path (Join-Path $repoRoot "frontend\node_modules"))) {
        throw "Frontend dependencies are missing. Run npm install in frontend first."
    }

    $startParameters = @{}
    if ($SkipBuild) {
        $startParameters.SkipBuild = $true
    }
    & (Join-Path $repoRoot "scripts\start_demo.ps1") @startParameters
    Assert-LastExitCode "Docker demo startup"

    $demoReportPath = Join-Path $repoRoot "var\demo\mvp-demo.json"
    if (-not (Test-Path $demoReportPath)) {
        throw "Fixed MVP demo report was not generated."
    }
    $demoReport = Get-Content -Raw -Encoding UTF8 $demoReportPath | ConvertFrom-Json
    if (-not $demoReport.all_passed) {
        throw "Fixed four-scenario MVP demo did not pass."
    }
    Add-Step "Docker + migration + seed + fixed demo" "PASS" "var/demo/mvp-demo.md; 4/4 scenarios"

    & docker compose ps
    Assert-LastExitCode "Docker Compose health check"
    $health = Invoke-RestMethod -Uri "http://localhost:8000/health" -Method Get
    if ($health.status -ne "ok") {
        throw "Backend health did not return status=ok."
    }
    $frontendResponse = Invoke-WebRequest -Uri "http://localhost:3000/" -UseBasicParsing
    if ($frontendResponse.StatusCode -ne 200) {
        throw "Frontend health returned HTTP $($frontendResponse.StatusCode)."
    }
    Add-Step "Backend/frontend HTTP smoke" "PASS" "backend /health=200; frontend /=200"

    $env:PYTHONPATH = (Join-Path $repoRoot "backend")
    $env:PYTHONPYCACHEPREFIX = (Join-Path $repoRoot "output\pycache-4c-closeout")
    New-Item -ItemType Directory -Force -Path (Join-Path $repoRoot "output") | Out-Null
    & $pythonPath -m app.agent.harness_runner
    Assert-LastExitCode "Deterministic Agent Harness"
    & $pythonPath -m app.agent.ablation_harness
    Assert-LastExitCode "A/B/C ablation Harness"
    if (-not (Test-Path (Join-Path $repoRoot "docs\agent_eval_report.example.md"))) {
        throw "Agent evaluation report was not generated."
    }
    if (-not (Test-Path (Join-Path $repoRoot "output\agent_ablation_report.4b.json"))) {
        throw "A/B/C ablation report was not generated."
    }
    Add-Step "Deterministic Harness + A/B/C ablation" "PASS" "docs/agent_eval_report.example.md; output/agent_ablation_report.4b.json"

    Push-Location (Join-Path $repoRoot "frontend")
    try {
        $env:E2E_BROWSER_CHANNEL = "msedge"
        & npm.cmd run test:e2e
        Assert-LastExitCode "Browser E2E"
    }
    finally {
        Pop-Location
    }
    Add-Step "Browser E2E" "PASS" "Playwright + Edge; 7 scenarios"

    $closeoutStatus = "PASS"
    Write-Host "4C-4 MVP closeout passed."
}
catch {
    $failureMessage = $_.Exception.Message
    Add-Step "Closeout execution" "FAIL" $failureMessage
    Write-Error $failureMessage
}
finally {
    Write-CloseoutReports -Status $closeoutStatus -Failure $failureMessage
    Pop-Location
}

if ($closeoutStatus -ne "PASS") {
    exit 1
}
