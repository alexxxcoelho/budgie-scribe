$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$releaseScript = Join-Path $repoRoot "scripts\windows\release-scribe.ps1"
$tokens = $null
$parseErrors = $null
[void][Management.Automation.Language.Parser]::ParseFile($releaseScript, [ref]$tokens, [ref]$parseErrors)
if ($parseErrors.Count -ne 0) { throw "Parser errors: $($parseErrors.Message -join '; ')" }

. $releaseScript -LocalPath "unused"
$tempDir = Join-Path ([IO.Path]::GetTempPath()) ("scribe-release-test-" + [Guid]::NewGuid())
New-Item -ItemType Directory -Path $tempDir | Out-Null
try {
    $missing = Join-Path $tempDir "scribe-v8-Q4_K_M.gguf"
    try {
        Assert-ReleaseFile -Path $missing -ExpectedName "scribe-v8-Q4_K_M.gguf" -ExpectedSize 4 -ExpectedSha256 "0000"
        throw "Missing artifact was accepted."
    } catch { if ($_.Exception.Message -eq "Missing artifact was accepted.") { throw } }

    $wrongName = Join-Path $tempDir "scribe-v7-Q4_K_M.gguf"
    [IO.File]::WriteAllBytes($wrongName, [byte[]](1, 2, 3, 4))
    try {
        Assert-ReleaseFile -Path $wrongName -ExpectedName "scribe-v8-Q4_K_M.gguf" -ExpectedSize 4 `
            -ExpectedSha256 "9f64a747e1b97f131fabb6b447296c9b6f0201e79fb3c5356e6c77e89b6a806a"
        throw "Wrong model name was accepted."
    } catch { if ($_.Exception.Message -eq "Wrong model name was accepted.") { throw } }

    $candidate = Join-Path $tempDir "scribe-v8-Q4_K_M.gguf"
    [IO.File]::WriteAllBytes($candidate, [byte[]](1, 2, 3, 4))
    try {
        Assert-ReleaseFile -Path $candidate -ExpectedName "scribe-v8-Q4_K_M.gguf" -ExpectedSize 5 `
            -ExpectedSha256 "9f64a747e1b97f131fabb6b447296c9b6f0201e79fb3c5356e6c77e89b6a806a"
        throw "Wrong artifact size was accepted."
    } catch { if ($_.Exception.Message -eq "Wrong artifact size was accepted.") { throw } }

    $validated = Assert-ReleaseFile -Path $candidate -ExpectedName "scribe-v8-Q4_K_M.gguf" `
        -ExpectedSize 4 -ExpectedSha256 "9f64a747e1b97f131fabb6b447296c9b6f0201e79fb3c5356e6c77e89b6a806a"
    if ($validated.Size -ne 4) { throw "Valid fixture did not pass validation." }

    # The release table is the only authority on what may be published.
    $pinned = Resolve-ScribeRelease -Path (Join-Path $tempDir "scribe-v8-Q4_K_M.gguf")
    if ($pinned.Language -ne "fr" -or $pinned.Size -ne 396704576) { throw "French release was not resolved from its file name." }
    foreach ($release in $script:ScribeReleases) {
        if ($release.Sha256 -notmatch '^[0-9a-f]{64}$') { throw "Release $($release.FileName) has no pinned SHA-256." }
        if ($release.Size -le 0) { throw "Release $($release.FileName) has no pinned size." }
        if ($release.NoticeRemoteKey -notlike "models/*-NOTICE.txt") { throw "Release $($release.FileName) has no notice key." }
    }
    try {
        Resolve-ScribeRelease -Path (Join-Path $tempDir "scribe-v7-Q4_K_M.gguf") | Out-Null
        throw "Unpinned artifact was accepted."
    } catch { if ($_.Exception.Message -eq "Unpinned artifact was accepted.") { throw } }
} finally {
    Remove-Item -LiteralPath $tempDir -Recurse -Force
}

Write-Output "release-scribe validation tests passed"
