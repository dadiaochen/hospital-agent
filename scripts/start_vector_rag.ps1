param(
    [switch]$SkipBuild,
    [switch]$SkipScenarios
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$previousVectorEnabled = $env:RAG_VECTOR_ENABLED
$previousEmbeddingModel = $env:RAG_EMBEDDING_MODEL

Push-Location $repoRoot
try {
    New-Item -ItemType Directory -Force "var\models" | Out-Null
    $env:RAG_VECTOR_ENABLED = "true"
    $env:RAG_EMBEDDING_MODEL = "BAAI/bge-small-zh-v1.5"

    & (Join-Path $PSScriptRoot "start_demo.ps1") `
        -SkipBuild:$SkipBuild `
        -SkipScenarios:$SkipScenarios
    if ($LASTEXITCODE -ne 0) {
        throw "The vector RAG stack did not start successfully."
    }

    docker compose exec -T backend python -m scripts.check_vector_rag
    if ($LASTEXITCODE -ne 0) {
        throw "Vector RAG smoke verification did not produce a traceable vector hit."
    }

    Write-Host ""
    Write-Host "Vector RAG is active for this Compose deployment."
    Write-Host "Embedding cache: $repoRoot\var\models\fastembed"
}
finally {
    if ($null -eq $previousVectorEnabled) {
        Remove-Item Env:RAG_VECTOR_ENABLED -ErrorAction SilentlyContinue
    }
    else {
        $env:RAG_VECTOR_ENABLED = $previousVectorEnabled
    }
    if ($null -eq $previousEmbeddingModel) {
        Remove-Item Env:RAG_EMBEDDING_MODEL -ErrorAction SilentlyContinue
    }
    else {
        $env:RAG_EMBEDDING_MODEL = $previousEmbeddingModel
    }
    Pop-Location
}
