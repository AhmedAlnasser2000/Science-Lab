[CmdletBinding(SupportsShouldProcess = $true, ConfirmImpact = 'High')]
param(
    [string]$Branch,
    [string]$Path,
    [string]$Remote = 'origin',
    [string]$Base,
    [switch]$DeleteBranch,
    [switch]$ForceRemove,
    [switch]$ForceDeleteBranch
)

$ErrorActionPreference = 'Stop'
$global:PSNativeCommandUseErrorActionPreference = $false
$repoHint = Resolve-Path (Join-Path $PSScriptRoot '..\..') -ErrorAction SilentlyContinue
if ($repoHint) { Set-Location $repoHint }

function Fail-Exit {
    param([int]$Code, [string]$Message)
    Write-Error $Message
    exit $Code
}

function Invoke-Git {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$GitArgs,
        [switch]$AllowFailure,
        [string]$WorkingDirectory
    )
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

    if (-not $AllowFailure -and $code -ne 0) {
        Fail-Exit -Code 3 -Message "Command failed ($code): git $($GitArgs -join ' ')`n$($output -join "`n")"
    }

    [PSCustomObject]@{ ExitCode = $code; Output = ($output -join "`n").Trim() }
}

function Get-RepoRoot {
    $res = Invoke-Git -GitArgs @('rev-parse', '--show-toplevel') -AllowFailure
    if ($res.ExitCode -ne 0 -or [string]::IsNullOrWhiteSpace($res.Output)) {
        Fail-Exit -Code 2 -Message 'Not inside a git repository.'
    }
    $res.Output.Trim()
}

function Get-WorktreeRecords {
    $res = Invoke-Git -GitArgs @('worktree', 'list', '--porcelain')
    $records = @()
    $current = $null
    foreach ($line in ($res.Output -split "`n")) {
        $l = $line.Trim()
        if (-not $l) {
            if ($null -ne $current) { $records += $current; $current = $null }
            continue
        }
        if ($l.StartsWith('worktree ')) {
            if ($null -ne $current) { $records += $current }
            $current = [ordered]@{ path = $l.Substring(9).Trim(); branch = $null }
            continue
        }
        if ($null -eq $current) { continue }
        if ($l.StartsWith('branch ')) {
            $ref = $l.Substring(7).Trim()
            $current.branch = $ref -replace '^refs/heads/', ''
        }
    }
    if ($null -ne $current) { $records += $current }
    return $records
}

function Resolve-Target {
    param([string]$BranchArg, [string]$PathArg)
    $records = Get-WorktreeRecords

    if ($PathArg) {
        $full = [System.IO.Path]::GetFullPath($PathArg)
        $match = $records | Where-Object { [System.IO.Path]::GetFullPath($_.path) -eq $full } | Select-Object -First 1
        return [PSCustomObject]@{ path = $full; branch = $match.branch; registered = ($null -ne $match) }
    }

    if (-not $BranchArg) {
        Fail-Exit -Code 2 -Message 'Provide -Branch or -Path.'
    }

    $m2 = $records | Where-Object { $_.branch -eq $BranchArg } | Select-Object -First 1
    if ($null -eq $m2) {
        Fail-Exit -Code 2 -Message "No registered worktree found for branch '$BranchArg'."
    }

    [PSCustomObject]@{ path = [System.IO.Path]::GetFullPath($m2.path); branch = $m2.branch; registered = $true }
}

$repoRoot = Get-RepoRoot
Set-Location $repoRoot

$target = Resolve-Target -BranchArg $Branch -PathArg $Path
if (-not $target.registered -and -not $ForceRemove) {
    Fail-Exit -Code 2 -Message "Path is not a registered git worktree: $($target.path). Use -ForceRemove to proceed."
}

if (-not (Test-Path $target.path)) {
    Fail-Exit -Code 2 -Message "Worktree path does not exist: $($target.path)"
}

$metaPath = Join-Path $target.path '.physicslab_worktree.json'
$meta = $null
if (Test-Path $metaPath) {
    try { $meta = Get-Content $metaPath -Raw | ConvertFrom-Json } catch { $meta = $null }
}

if ($Branch -and $Path -and $meta -and $meta.branch -and ($meta.branch -ne $Branch)) {
    Fail-Exit -Code 2 -Message "Provided -Branch ('$Branch') does not match metadata branch ('$($meta.branch)')."
}

$status = Invoke-Git -GitArgs @('status', '--porcelain') -WorkingDirectory $target.path
if (-not [string]::IsNullOrWhiteSpace($status.Output)) {
    Fail-Exit -Code 2 -Message "Worktree has uncommitted changes: $($target.path). Clean it before removal."
}

if ($PSCmdlet.ShouldProcess($target.path, 'Remove git worktree')) {
    Invoke-Git -GitArgs @('worktree', 'remove', $target.path) | Out-Null
    Write-Host "[ok] Removed worktree: $($target.path)"
}

if ($DeleteBranch) {
    $resolvedBranch = if ($Branch) { $Branch } elseif ($target.branch) { $target.branch } elseif ($meta -and $meta.branch) { [string]$meta.branch } else { $null }
    if (-not $resolvedBranch) {
        Fail-Exit -Code 2 -Message 'Cannot determine branch name for deletion. Pass -Branch explicitly.'
    }

    $resolvedBase = if ($Base) { $Base } elseif ($meta -and $meta.base) { [string]$meta.base } else { "$Remote/main" }

    $countRes = Invoke-Git -GitArgs @('rev-list', '--count', "$resolvedBase..$resolvedBranch") -AllowFailure
    if ($countRes.ExitCode -ne 0) {
        Fail-Exit -Code 3 -Message "Failed to compare '$resolvedBranch' against base '$resolvedBase'."
    }

    $ahead = 0
    [void][int]::TryParse($countRes.Output, [ref]$ahead)

    if ($ahead -gt 0 -and -not $ForceDeleteBranch) {
        Fail-Exit -Code 2 -Message "Branch '$resolvedBranch' has $ahead commit(s) not in '$resolvedBase'. Re-run with -ForceDeleteBranch to delete anyway."
    }

    if ($ForceDeleteBranch) {
        Invoke-Git -GitArgs @('branch', '-D', $resolvedBranch) | Out-Null
    } else {
        Invoke-Git -GitArgs @('branch', '-d', $resolvedBranch) | Out-Null
    }
    Write-Host "[ok] Deleted local branch: $resolvedBranch"
}

$hintBranch = if ($Branch) { $Branch } elseif ($target.branch) { $target.branch } else { '<branch>' }
Write-Host "[next] Re-create with: powershell ./tools/dev/start_slice_worktree.ps1 -Branch $hintBranch"

exit 0
