param()

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$includeRoots = @("productpulse", "tests", "migrations", "frontend", "scripts", "data/dev")
$rootFiles = @(
    ".env.example",
    ".python-version",
    "alembic.ini",
    "index.html",
    "package.json",
    "package-lock.json",
    "pyproject.toml",
    "tsconfig.json",
    "uv.lock",
    "vite.config.ts",
    "tooling/uv.version",
    "docs/PRE_MERGE_CHECKLIST.md"
)

$excludedDirectoryNames = @(
    "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".hypothesis",
    ".tox", ".nox", ".venv", "venv", "venv.bak", "env", "env.bak",
    ".tools", "node_modules", ".cache", "cache", "caches", ".eslintcache",
    ".vite", ".vitest", ".turbo", ".next", ".nuxt", ".parcel-cache",
    ".svelte-kit", ".pytest-temp", ".gradle", ".vercel", ".netlify",
    ".serverless", ".angular", "storybook-static",
    "dist", "build", "coverage", "htmlcov", "target", "out", ".python_env",
    "site-packages"
)
$excludedFilePatterns = @(
    '(?i)\.py[co]$',
    '(?i)\.pyd$',
    '(?i)\.tsbuildinfo$',
    '(?i)^\.coverage(?:\..*)?$',
    '(?i)^coverage\.(?:xml|json)$',
    '(?i)\.cache$',
    '(?i)\.(?:log|tmp)$',
    '(?i)^npm-debug\.log(?:\.\d+)?$',
    '(?i)^(?:\.DS_Store|Thumbs\.db)$'
)

function Test-ExcludedFingerprintFile {
    param([Parameter(Mandatory = $true)][System.IO.FileInfo]$File)

    if (($File.Name -match '(?i)^\.env(?:$|\.)' -or $File.Name -match '(?i)\.env$') -and $File.Name -ne ".env.example") {
        return $true
    }

    foreach ($pattern in $excludedFilePatterns) {
        if ($File.Name -match $pattern) {
            return $true
        }
    }

    return $false
}

function Get-FingerprintFiles {
    param([Parameter(Mandatory = $true)][string]$Directory)

    foreach ($entry in Get-ChildItem -LiteralPath $Directory -Force) {
        if ($entry.Attributes -band [System.IO.FileAttributes]::ReparsePoint) {
            continue
        }

        if ($entry.PSIsContainer) {
            if ($excludedDirectoryNames -contains $entry.Name) {
                continue
            }

            Get-FingerprintFiles -Directory $entry.FullName
            continue
        }

        if (-not (Test-ExcludedFingerprintFile -File $entry)) {
            $entry
        }
    }
}

$relativePaths = New-Object 'System.Collections.Generic.List[string]'
foreach ($relative in $rootFiles) {
    $path = Join-Path $repoRoot ($relative.Replace("/", "\"))
    if (Test-Path -LiteralPath $path -PathType Leaf) {
        $relativePaths.Add($relative.Replace("\", "/"))
    }
}

foreach ($root in $includeRoots) {
    $path = Join-Path $repoRoot ($root.Replace("/", "\"))
    if (Test-Path -LiteralPath $path -PathType Container) {
        foreach ($file in Get-FingerprintFiles -Directory $path) {
            $relative = $file.FullName.Substring($repoRoot.Length + 1).Replace("\", "/")
            $relativePaths.Add($relative)
        }
    }
}

$sortedRelativePaths = [string[]]$relativePaths.ToArray()
[System.Array]::Sort($sortedRelativePaths, [System.StringComparer]::Ordinal)
$manifestLines = @(
    foreach ($relative in $sortedRelativePaths) {
        $path = Join-Path $repoRoot ($relative.Replace("/", "\"))
        $hash = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
        "$relative`t$hash"
    }
)
$manifest = [string]::Join("`n", $manifestLines)
$sha256 = [System.Security.Cryptography.SHA256]::Create()
try {
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($manifest)
    $digest = [System.BitConverter]::ToString($sha256.ComputeHash($bytes)).Replace("-", "").ToLowerInvariant()
} finally {
    $sha256.Dispose()
}

Write-Output "Implementation source snapshot v2 SHA-256 (generated artifacts excluded): $digest"
Write-Output "Files included: $($manifestLines.Count)"
