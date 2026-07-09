<#
.SYNOPSIS
    Deploy the current feature/pruebaGon state to the shared PRE environment.

.DESCRIPTION
    Pushes your integration branch (feature/pruebaGon) and then updates the
    mirror branch (feature/pre_pruebaGon), which triggers the `deploy-pre`
    GitHub Action (rebuild dp-pre-bot + reindex KB + health check).

    It does NOT run on every commit — only when you run this — so a routine
    commit doesn't rebuild PRE. See docs/deploy-pre-redeploy.md.

    PowerShell equivalent of scripts/deploy_pre_gon.sh (for Windows/PowerShell,
    where `bash` may not be available).

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\deploy_pre_gon.ps1
.EXAMPLE
    .\scripts\deploy_pre_gon.ps1 -Yes -SkipLint
#>
[CmdletBinding()]
param(
    [string]$DevBranch = "feature/pruebaGon",
    [string]$PreBranch = "feature/pre_pruebaGon",
    [string]$Remote    = "origin",
    [switch]$SkipLint,   # skip the local `ruff check src` pre-check
    [switch]$Yes         # don't ask for confirmation
)

$ErrorActionPreference = "Stop"

# Move to the repo root.
$repoRoot = (git rev-parse --show-toplevel).Trim()
Set-Location $repoRoot

# 1) Warn about uncommitted work — the deploy uses the COMMITTED state.
if (git status --porcelain) {
    Write-Host "ADVERTENCIA: Tienes cambios sin commitear. El deploy usa lo COMMITEADO, no tu working tree." -ForegroundColor Yellow
    Write-Host "             Commitea primero si quieres que esos cambios lleguen a PRE." -ForegroundColor Yellow
}

# 2) Local lint pre-check (CI enforces this; fail fast before triggering a deploy).
if (-not $SkipLint) {
    if (Get-Command ruff -ErrorAction SilentlyContinue) {
        Write-Host "==> ruff check src"
        ruff check src
        if ($LASTEXITCODE -ne 0) { throw "ruff falló — arregla el lint antes de desplegar (o usa -SkipLint)." }
    } else {
        Write-Host "    (ruff no instalado; me lo salto — el CI igual lo corre)" -ForegroundColor DarkGray
    }
}

# 3) Confirm — PRE is a SINGLE shared environment (Gadea / Alvaro / you).
$currentHead = (git rev-parse --short HEAD).Trim()
Write-Host ""
Write-Host "Vas a desplegar '$DevBranch' ($currentHead) a la PRE COMPARTIDA via '$PreBranch'."
Write-Host "Esto sobreescribe lo que haya desplegado ahora mismo (avisa al equipo)."
if (-not $Yes) {
    $ans = Read-Host "Continuar? [y/N]"
    if ($ans -notin @("y", "Y", "yes", "YES")) {
        Write-Host "Cancelado."
        exit 1
    }
}

# 4) Push your integration branch, then update the mirror to trigger the deploy.
Write-Host "==> Pushing $DevBranch"
git push $Remote $DevBranch
if ($LASTEXITCODE -ne 0) { throw "git push $DevBranch falló." }

Write-Host "==> Updating mirror $PreBranch -> triggers deploy-pre"
git push $Remote "${DevBranch}:${PreBranch}" --force-with-lease
if ($LASTEXITCODE -ne 0) { throw "git push del espejo falló." }

Write-Host ""
Write-Host "OK. La Action 'CI' del branch $PreBranch corre Lint+Tests y luego 'Deploy to PRE'." -ForegroundColor Green
Write-Host "    Miralo en la pestana Actions de GitHub (adminiscore/diving-planet-bot)."
