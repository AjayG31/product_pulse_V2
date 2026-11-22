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

$selected = @()
foreach ($relative in $rootFiles) {
    $path = Join-Path $repoRoot ($relative.Replace("/", "\"))
    if (Test-Path -LiteralPath $path -PathType Leaf) {
        $selected += Get-Item -LiteralPath $path
    }
}

foreach ($root in $includeRoots) {
    $path = Join-Path $repoRoot ($root.Replace("/", "\"))
    if (Test-Path -LiteralPath $path -PathType Container) {
        $selected += Get-ChildItem -LiteralPath $path -File -Recurse
    }
}

$manifestLines = @(
    $selected |
        Sort-Object FullName -Unique |
        ForEach-Object {
            $relative = $_.FullName.Substring($repoRoot.Length + 1).Replace("\", "/")
            $hash = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
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

Write-Output "Implementation source snapshot SHA-256: $digest"
Write-Output "Files included: $($manifestLines.Count)"

