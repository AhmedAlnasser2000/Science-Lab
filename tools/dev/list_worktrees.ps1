[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$global:PSNativeCommandUseErrorActionPreference = $false
$repoHint = Resolve-Path (Join-Path $PSScriptRoot '..\..') -ErrorAction SilentlyContinue
if ($repoHint) { Set-Location $repoHint }

function Invoke-Git {
    param([string[]]$GitArgs, [string]$WorkingDirectory)
    $prevEap = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        if ($WorkingDirectory) {
            $output = & git -C $WorkingDirectory @GitArgs 2>&1
        } else {
            $output = & git @GitArgs 2>&1
        }
    } finally {
        $ErrorActionPreference = $prevEap
    }
    $code = $LASTEXITCODE
    [PSCustomObject]@{ ExitCode = $code; Output = ($output -join "`n").Trim() }
}

function Test-WorktreeDirty {
    param([string]$WorktreePath)
    $st = Invoke-Git -GitArgs @('status', '--porcelain') -WorkingDirectory $WorktreePath
    if ([string]::IsNullOrWhiteSpace($st.Output)) {
        return $false
    }
    $lines = $st.Output -split "`n" | ForEach-Object { $_.Trim() } | Where-Object { $_ }
    $filtered = $lines | Where-Object {
        ($_ -ne '?? .physicslab_worktree.json') -and
        ($_ -ne '?? .physicslab_worktree.json`r')
    }
    return $filtered.Count -gt 0
}

$res = Invoke-Git -GitArgs @('worktree', 'list', '--porcelain')
if ($res.ExitCode -ne 0) {
    Write-Error "Failed to list worktrees.`n$($res.Output)"
    exit 2
}

Write-Host 'Registered worktrees:'
$plain = Invoke-Git -GitArgs @('worktree', 'list')
Write-Host $plain.Output
Write-Host ''

$records = @()
$current = $null
foreach ($line in ($res.Output -split "`n")) {
    $l = $line.Trim()
    if (-not $l) {
        if ($current) { $records += $current; $current = $null }
        continue
    }

    if ($l.StartsWith('worktree ')) {
        if ($current) { $records += $current }
        $current = [ordered]@{ path = $l.Substring(9).Trim(); branch = '-' }
        continue
    }

    if ($current -and $l.StartsWith('branch ')) {
        $current.branch = ($l.Substring(7).Trim() -replace '^refs/heads/', '')
    }
}
if ($current) { $records += $current }

$rows = @()
foreach ($r in $records) {
    if (-not (Test-Path $r.path)) {
        $dirty = 'missing'
    } else {
        $dirty = if (Test-WorktreeDirty -WorktreePath $r.path) { 'dirty' } else { 'clean' }
    }
    $rows += [PSCustomObject]@{
        Branch = $r.branch
        Status = $dirty
        Path = $r.path
    }
}

if ($rows.Count -gt 0) {
    $rows | Format-Table -AutoSize
} else {
    Write-Host '(none)'
}

Write-Host ''
Write-Host 'Cleanup example:'
Write-Host '  powershell ./tools/dev/remove_slice_worktree.ps1 -Branch work/vX.Yz -DeleteBranch'

exit 0
