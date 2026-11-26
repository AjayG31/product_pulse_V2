param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("PP-010", "PP-011", "PP-012", "PP-013", "PP-014", "PP-023", "PP-029", "PP-037", "PP-048")]
    [string]$Ticket,

    [string]$EvidencePath
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $repoRoot

if ([string]::IsNullOrWhiteSpace($EvidencePath)) {
    $evidenceMilestone = if ($Ticket -in @("PP-029", "PP-037", "PP-048")) { "m4" } elseif ($Ticket -in @("PP-012", "PP-013", "PP-014")) { "m2" } else { "m1" }
    $EvidencePath = "docs/evidence/$evidenceMilestone/$Ticket.txt"
}
$evidenceFile = Join-Path $repoRoot $EvidencePath
$evidenceDirectory = Split-Path -Parent $evidenceFile
New-Item -ItemType Directory -Force -Path $evidenceDirectory | Out-Null

$transcriptStarted = $false
try {
    Start-Transcript -Path $evidenceFile -Force | Out-Null
    $transcriptStarted = $true

    $uvPath = Join-Path $repoRoot ".tools/bin/uv.exe"
    if (-not (Test-Path -LiteralPath $uvPath -PathType Leaf)) {
        $uvCommand = Get-Command uv.exe -ErrorAction SilentlyContinue
        if (-not $uvCommand) {
            throw "uv is not available. Install the release pinned in tooling/uv.version and retry."
        }
        $uvPath = $uvCommand.Source
    }

    $expectedUv = (Get-Content -LiteralPath (Join-Path $repoRoot "tooling/uv.version") -Raw).Trim()
    $actualUv = (& $uvPath --version | Out-String).Trim()
    if ($LASTEXITCODE -ne 0 -or $actualUv -notmatch "^uv $([regex]::Escape($expectedUv))(\s|$)") {
        throw "Expected uv $expectedUv; found '$actualUv'."
    }
    Write-Output "uv: $actualUv"

    $npmPath = Join-Path $repoRoot ".tools/npm/node_modules/.bin/npm.cmd"
    if (-not (Test-Path -LiteralPath $npmPath -PathType Leaf)) {
        $npmPath = Join-Path $env:ProgramFiles "nodejs/npm.cmd"
    }
    if (-not (Test-Path -LiteralPath $npmPath -PathType Leaf)) {
        $npmCommand = Get-Command npm.cmd -ErrorAction SilentlyContinue
        if (-not $npmCommand) {
            throw "npm.cmd is not available."
        }
        $npmPath = $npmCommand.Source
    }

    $nodeVersionText = (& node --version | Out-String).Trim().TrimStart("v")
    if ($LASTEXITCODE -ne 0 -or [version]$nodeVersionText -lt [version]"22.22.0") {
        throw "Node.js 22.22.0 or newer is required; found '$nodeVersionText'."
    }
    $npmVersion = (& $npmPath --version | Out-String).Trim()
    if ($LASTEXITCODE -ne 0 -or $npmVersion -ne "11.20.0") {
        throw "npm 11.20.0 is pinned for this setup; found '$npmVersion'."
    }
    Write-Output "Node.js: $nodeVersionText"
    Write-Output "npm: $npmVersion"

    $env:UV_CACHE_DIR = Join-Path $repoRoot ".tools/cache"
    $env:UV_PYTHON_INSTALL_DIR = Join-Path $repoRoot ".tools/python"
    $env:npm_config_cache = Join-Path $repoRoot ".tools/npm-cache"
    $pytestTempRoot = Join-Path $repoRoot ".tools/pytest-temp"
    New-Item -ItemType Directory -Force -Path $pytestTempRoot | Out-Null
    $env:TEMP = $pytestTempRoot
    $env:TMP = $pytestTempRoot
    $env:TMPDIR = $pytestTempRoot
    $pytestBase = Join-Path $pytestTempRoot ("$Ticket-" + [guid]::NewGuid().ToString("N"))
    $pythonVersion = (& $uvPath run --locked python --version | Out-String).Trim()
    if ($LASTEXITCODE -ne 0 -or $pythonVersion -notmatch "^Python 3\.12\.") {
        throw "CPython 3.12 is required; found '$pythonVersion'."
    }
    Write-Output "Python: $pythonVersion"

    function Invoke-ExternalCheck {
        param(
            [Parameter(Mandatory = $true)][string]$Name,
            [Parameter(Mandatory = $true)][string]$FilePath,
            [Parameter(Mandatory = $true)][string[]]$Arguments
        )

        Write-Output "`n===== $Name ====="
        & $FilePath @Arguments
        if ($LASTEXITCODE -ne 0) {
            throw "$Name failed with exit code $LASTEXITCODE."
        }
    }

    function Invoke-BanditCheck {
        param([Parameter(Mandatory = $true)][string]$Name)

        $previousLocalAppData = $env:LOCALAPPDATA
        $env:LOCALAPPDATA = Join-Path $repoRoot ".tools/cache/appdata"
        New-Item -ItemType Directory -Force -Path $env:LOCALAPPDATA | Out-Null
        try {
            Invoke-ExternalCheck -Name $Name -FilePath $uvPath -Arguments @("run", "--locked", "bandit", "-r", "productpulse")
        } finally {
            $env:LOCALAPPDATA = $previousLocalAppData
        }
    }

    switch ($Ticket) {
        "PP-010" {
            $pythonTests = @(
                "tests/test_settings.py",
                "tests/test_logging_config.py",
                "tests/test_database.py",
                "tests/test_health.py",
                "tests/test_migrations.py",
                "tests/test_worker_entry.py"
            )
            Invoke-ExternalCheck -Name "PP-010 pytest / FastAPI TestClient" -FilePath $uvPath -Arguments (@("run", "--locked", "pytest", "-q", "-p", "no:cacheprovider", "--basetemp", $pytestBase) + $pythonTests)
            Invoke-ExternalCheck -Name "PP-010 Vitest / React Testing Library" -FilePath $npmPath -Arguments @("run", "test")
            Invoke-ExternalCheck -Name "PP-010 frontend production build" -FilePath $npmPath -Arguments @("run", "build")
            Invoke-BanditCheck -Name "PP-010 Bandit"
            Invoke-ExternalCheck -Name "PP-010 pip-audit" -FilePath $uvPath -Arguments @("run", "--locked", "pip-audit")
            Invoke-ExternalCheck -Name "PP-010 npm audit" -FilePath $npmPath -Arguments @("audit")
        }
        "PP-011" {
            Invoke-ExternalCheck -Name "PP-011 deterministic synthetic corpus generation" -FilePath $uvPath -Arguments @("run", "--locked", "python", "-m", "productpulse.datasets.generate", "--output", "data/dev")
            Invoke-ExternalCheck -Name "PP-011 pytest" -FilePath $uvPath -Arguments @("run", "--locked", "pytest", "-q", "-p", "no:cacheprovider", "--basetemp", $pytestBase, "tests/test_synthetic_data.py")
            Invoke-BanditCheck -Name "PP-011 Bandit"
            Invoke-ExternalCheck -Name "PP-011 pip-audit" -FilePath $uvPath -Arguments @("run", "--locked", "pip-audit")
        }
        "PP-012" {
            $pythonTests = @(
                "tests/test_settings.py",
                "tests/test_logging_config.py",
                "tests/test_database.py",
                "tests/test_health.py",
                "tests/test_migrations.py",
                "tests/test_auth.py"
            )
            Invoke-ExternalCheck -Name "PP-012 pytest / FastAPI TestClient" -FilePath $uvPath -Arguments (@("run", "--locked", "pytest", "-q", "-p", "no:cacheprovider", "--basetemp", $pytestBase) + $pythonTests)
            Invoke-ExternalCheck -Name "PP-012 Vitest / React Testing Library" -FilePath $npmPath -Arguments @("run", "test")
            Invoke-ExternalCheck -Name "PP-012 frontend production build" -FilePath $npmPath -Arguments @("run", "build")
            Invoke-BanditCheck -Name "PP-012 Bandit"
            Invoke-ExternalCheck -Name "PP-012 pip-audit" -FilePath $uvPath -Arguments @("run", "--locked", "pip-audit")
            Invoke-ExternalCheck -Name "PP-012 npm audit" -FilePath $npmPath -Arguments @("audit")
        }
        "PP-013" {
            $pythonTests = @(
                "tests/test_settings.py",
                "tests/test_logging_config.py",
                "tests/test_database.py",
                "tests/test_health.py",
                "tests/test_migrations.py",
                "tests/test_auth.py",
                "tests/test_ingestion_preview.py"
            )
            Invoke-ExternalCheck -Name "PP-013 pytest / FastAPI TestClient" -FilePath $uvPath -Arguments (@("run", "--locked", "pytest", "-q", "-p", "no:cacheprovider", "--basetemp", $pytestBase) + $pythonTests)
            Invoke-ExternalCheck -Name "PP-013 Vitest / React Testing Library" -FilePath $npmPath -Arguments @("run", "test")
            Invoke-ExternalCheck -Name "PP-013 frontend production build" -FilePath $npmPath -Arguments @("run", "build")
            Invoke-BanditCheck -Name "PP-013 Bandit"
            Invoke-ExternalCheck -Name "PP-013 pip-audit" -FilePath $uvPath -Arguments @("run", "--locked", "pip-audit")
            Invoke-ExternalCheck -Name "PP-013 npm audit" -FilePath $npmPath -Arguments @("audit")
        }
        "PP-014" {
            Invoke-ExternalCheck -Name "PP-014 pytest / FastAPI TestClient" -FilePath $uvPath -Arguments @("run", "--locked", "pytest", "-q", "-p", "no:cacheprovider", "--basetemp", $pytestBase)
            Invoke-ExternalCheck -Name "PP-014 Vitest / React Testing Library" -FilePath $npmPath -Arguments @("run", "test")
            Invoke-ExternalCheck -Name "PP-014 frontend production build" -FilePath $npmPath -Arguments @("run", "build")
            Invoke-BanditCheck -Name "PP-014 Bandit"
            Invoke-ExternalCheck -Name "PP-014 pip-audit" -FilePath $uvPath -Arguments @("run", "--locked", "pip-audit")
            Invoke-ExternalCheck -Name "PP-014 npm audit" -FilePath $npmPath -Arguments @("audit")
        }
        "PP-023" {
            Invoke-ExternalCheck -Name "PP-023 pytest" -FilePath $uvPath -Arguments @("run", "--locked", "pytest", "-q", "-p", "no:cacheprovider", "--basetemp", $pytestBase, "tests/test_incident_logic.py")
            Invoke-BanditCheck -Name "PP-023 Bandit"
            Invoke-ExternalCheck -Name "PP-023 pip-audit" -FilePath $uvPath -Arguments @("run", "--locked", "pip-audit")
        }
        "PP-029" {
            $securityTests = @(
                "tests/test_auth.py",
                "tests/test_conflict_resolution.py",
                "tests/test_ingestion_confirmation.py",
                "tests/test_ingestion_preview.py",
                "tests/test_ingestion_reports.py",
                "tests/test_ingestion_retries.py",
                "tests/test_linkage_reconciliation.py"
            )
            Invoke-ExternalCheck -Name "PP-029 focused authentication and Admin-boundary pytest" -FilePath $uvPath -Arguments (@("run", "--locked", "pytest", "-q", "-p", "no:cacheprovider", "--basetemp", $pytestBase) + $securityTests)
            Invoke-ExternalCheck -Name "PP-029 full backend regression pytest" -FilePath $uvPath -Arguments @("run", "--locked", "pytest", "-q", "-p", "no:cacheprovider", "--basetemp", $pytestBase)
            Invoke-BanditCheck -Name "PP-029 Bandit"
            Invoke-ExternalCheck -Name "PP-029 pip-audit" -FilePath $uvPath -Arguments @("run", "--locked", "pip-audit")
        }
        "PP-037" {
            Invoke-ExternalCheck -Name "PP-037 existing user-management API pytest" -FilePath $uvPath -Arguments @("run", "--locked", "pytest", "-q", "-p", "no:cacheprovider", "--basetemp", $pytestBase, "tests/test_auth.py")
            Invoke-ExternalCheck -Name "PP-037 targeted Vitest / React Testing Library" -FilePath $npmPath -Arguments @("run", "test", "--", "frontend/src/UserManagement.test.tsx")
            Invoke-ExternalCheck -Name "PP-037 full Vitest / React Testing Library" -FilePath $npmPath -Arguments @("run", "test")
            Invoke-ExternalCheck -Name "PP-037 frontend type-check and production build" -FilePath $npmPath -Arguments @("run", "build")
            Invoke-ExternalCheck -Name "PP-037 npm audit" -FilePath $npmPath -Arguments @("audit")
        }
        "PP-048" {
            Invoke-ExternalCheck -Name "PP-048 existing conflict API pytest" -FilePath $uvPath -Arguments @("run", "--locked", "pytest", "-q", "-p", "no:cacheprovider", "--basetemp", $pytestBase, "tests/test_conflict_resolution.py")
            Invoke-ExternalCheck -Name "PP-048 targeted Vitest / React Testing Library" -FilePath $npmPath -Arguments @("run", "test", "--", "frontend/src/ConflictReview.test.tsx")
            Invoke-ExternalCheck -Name "PP-048 full Vitest / React Testing Library" -FilePath $npmPath -Arguments @("run", "test")
            Invoke-ExternalCheck -Name "PP-048 frontend type-check and production build" -FilePath $npmPath -Arguments @("run", "build")
            Invoke-ExternalCheck -Name "PP-048 npm audit" -FilePath $npmPath -Arguments @("audit")
        }
    }

    Write-Output "`n===== source snapshot identity ====="
    & (Join-Path $PSScriptRoot "source-fingerprint.ps1")
    if ($LASTEXITCODE -ne 0) {
        throw "Source fingerprint failed with exit code $LASTEXITCODE."
    }
    Write-Output "`nTicket $Ticket local checks passed."
} catch {
    Write-Error $_
    exit 1
} finally {
    if ($transcriptStarted) {
        Stop-Transcript | Out-Null
    }
}

