[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$repoHint = Resolve-Path (Join-Path $PSScriptRoot '..\..') -ErrorAction SilentlyContinue
if ($repoHint) { Set-Location $repoHint }

function Invoke-Git {
    param([string[]]$GitArgs, [string]$WorkingDirectory)
    if ($WorkingDirectory) {
        $output = & git -C $WorkingDirectory @GitArgs 2>&1
    } else {
        $output = & git @GitArgs 2>&1
    }
    $code = $LASTEXITCODE
    [PSCustomObject]@{ ExitCode = $code; Output = ($output -join "`n").Trim() }
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
        $st = Invoke-Git -GitArgs @('status', '--porcelain') -WorkingDirectory $r.path
        $dirty = if ([string]::IsNullOrWhiteSpace($st.Output)) { 'clean' } else { 'dirty' }
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
