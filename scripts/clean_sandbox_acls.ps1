# Removes leftover AppContainer / capability SID ACEs (S-1-15-2-* and S-1-15-3-*)
# from the trees the old (removed) AppContainer sandbox dirtied. These additive
# ACEs block Low-integrity reads/execute, breaking the current Low-IL sandbox.
# The standard ALL APPLICATION PACKAGES (S-1-15-2-1) and ALL RESTRICTED
# APPLICATION PACKAGES (S-1-15-2-2) SIDs are preserved.
#
# Run from an ELEVATED PowerShell:
#   powershell -ExecutionPolicy Bypass -File C:\democrai\scripts\clean_sandbox_acls.ps1

$ErrorActionPreference = 'Continue'

# Roots that the AppContainer experiments touched. Adjust if your install/data
# live elsewhere. C:\ is cleaned non-recursively (only its own ACEs).
#
# Resolve the base Python from the venv's pyvenv.cfg (NOT `Get-Command python`,
# which may resolve to a different install or a Store stub).
$repo = Split-Path -Parent $PSScriptRoot
$pythonDir = $null
$pyvenv = Join-Path $repo '.venv\pyvenv.cfg'
if (Test-Path $pyvenv) {
    $homeLine = (Get-Content $pyvenv | Where-Object { $_ -match '^\s*home\s*=' } | Select-Object -First 1)
    if ($homeLine) { $pythonDir = ($homeLine -replace '^\s*home\s*=\s*', '').Trim() }
}

# Recursive roots: trees that received inheritable (OI)(CI) grants, so the ACE
# propagated to every child and must be stripped recursively.
$recursiveRoots = @(
    $repo,
    'C:\democrai_data',
    $pythonDir,
    "$env:APPDATA\democrai",
    "$env:LOCALAPPDATA\democrai",
    $env:TEMP,
    $env:TMP
) | Where-Object { $_ -and (Test-Path $_) } | Select-Object -Unique

# Ancestor dirs: the old ancestor-stat walk added a NON-inherited traverse ACE
# to every parent up to the drive root. Clean only the directory's own ACE
# (NEVER recurse these — they are huge system/profile trees).
$ancestorRoots = @(
    'C:\Users',
    $env:USERPROFILE,
    $env:APPDATA,
    $env:LOCALAPPDATA
) | Where-Object { $_ -and (Test-Path $_) } | Select-Object -Unique

function Get-PackageSids($path) {
    # icacls prints unresolved package SIDs literally; collect S-1-15-2/3 except
    # the two well-known package SIDs.
    $out = & icacls $path 2>$null
    $sids = [System.Collections.Generic.HashSet[string]]::new()
    foreach ($line in $out) {
        foreach ($m in [regex]::Matches($line, 'S-1-15-[23]-[0-9-]+')) {
            $sid = $m.Value
            if ($sid -ne 'S-1-15-2-1' -and $sid -ne 'S-1-15-2-2') { [void]$sids.Add($sid) }
        }
    }
    return $sids
}

# 1. Drive root + ancestor dirs — their own ACEs only (NEVER recurse these).
foreach ($root in (@('C:\') + $ancestorRoots)) {
    $sids = Get-PackageSids $root
    foreach ($sid in $sids) {
        Write-Host "$root  remove $sid (solo dir)"
        & icacls $root /remove:g "*$sid" | Out-Null
    }
}

# 2. Recursive roots.
foreach ($root in $recursiveRoots) {
    $sids = Get-PackageSids $root
    if ($sids.Count -eq 0) { Write-Host "$root : pulito"; continue }
    foreach ($sid in $sids) {
        Write-Host "$root  remove $sid (ricorsivo)"
        & icacls $root /remove:g "*$sid" /T /C /Q | Out-Null
    }
}

Write-Host "Fatto. Verifica con: icacls C:\democrai\.venv\pyvenv.cfg"
