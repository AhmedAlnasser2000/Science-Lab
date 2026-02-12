[CmdletBinding(SupportsShouldProcess = $true, ConfirmImpact = 'Medium')]
param(
    [Parameter(Mandatory = $true)]
    [string]$Branch,
    [string]$Base = 'origin/main',
    [string]$Remote = 'origin',
    [string]$WorktreesRoot = '..\_worktrees\PhysicsLab',
    [switch]$Push,
    [switch]$Force
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
        $msg = "Command failed ($code): git $($GitArgs -join ' ')`n$($output -join "`n")"
        Fail-Exit -Code 3 -Message $msg
    }

    return [PSCustomObject]@{
        ExitCode = $code
        Output = ($output -join "`n").Trim()
    }
}

function Get-RepoRoot {
    $res = Invoke-Git -GitArgs @('rev-parse', '--show-toplevel') -AllowFailure
    if ($res.ExitCode -ne 0 -or [string]::IsNullOrWhiteSpace($res.Output)) {
        Fail-Exit -Code 2 -Message 'Not inside a git repository. Run this from the repo root.'
    }
    return $res.Output.Trim()
}

function Ensure-CleanWorkingTree {
    $res = Invoke-Git -GitArgs @('status', '--porcelain')
    if (-not [string]::IsNullOrWhiteSpace($res.Output)) {
        Fail-Exit -Code 2 -Message "Working tree is dirty. Commit or stash changes first.`nSuggested: git status --short"
    }
}

function Ensure-CleanWorkingTreeAtPath {
    param([Parameter(Mandatory = $true)][string]$Path)
    $res = Invoke-Git -GitArgs @('status', '--porcelain') -WorkingDirectory $Path
    if (-not [string]::IsNullOrWhiteSpace($res.Output)) {
        Fail-Exit -Code 2 -Message "Working tree is dirty at '$Path'. Commit or stash changes first."
    }
}

function Test-RefExists {
    param([string]$Ref)
    $res = Invoke-Git -GitArgs @('rev-parse', '--verify', $Ref) -AllowFailure
    return $res.ExitCode -eq 0
}

function Get-AheadBehindCount {
    param(
        [string]$LeftRef,
        [string]$RightRef,
        [string]$WorkingDirectory
    )
    $res = Invoke-Git -GitArgs @('rev-list', '--left-right', '--count', "$LeftRef...$RightRef") -AllowFailure -WorkingDirectory $WorkingDirectory
    if ($res.ExitCode -ne 0 -or [string]::IsNullOrWhiteSpace($res.Output)) {
        Fail-Exit -Code 2 -Message "Unable to compare refs '$LeftRef' and '$RightRef'."
    }
    $parts = $res.Output -split '\s+'
    if ($parts.Count -lt 2) {
        Fail-Exit -Code 2 -Message "Unexpected rev-list output while comparing '$LeftRef' and '$RightRef': $($res.Output)"
    }
    return [PSCustomObject]@{
        Ahead = [int]$parts[0]
        Behind = [int]$parts[1]
    }
}

function Get-WorktreePathForBranch {
    param([string]$BranchName)
    $res = Invoke-Git -GitArgs @('worktree', 'list', '--porcelain')
    if ([string]::IsNullOrWhiteSpace($res.Output)) {
        return $null
    }
    $lines = $res.Output -split "`r?`n"
    $currentPath = $null
    foreach ($line in $lines) {
        if ($line -like 'worktree *') {
            $currentPath = $line.Substring(9).Trim()
            continue
        }
        if ($line -eq "branch refs/heads/$BranchName") {
            return $currentPath
        }
    }
    return $null
}

function Test-WorktreePathRegistered {
    param([Parameter(Mandatory = $true)][string]$Path)
    $res = Invoke-Git -GitArgs @('worktree', 'list', '--porcelain')
    if ([string]::IsNullOrWhiteSpace($res.Output)) {
        return $false
    }
    $needle = [System.IO.Path]::GetFullPath($Path).TrimEnd('\').ToLowerInvariant()
    $lines = $res.Output -split "`r?`n"
    foreach ($line in $lines) {
        if ($line -like 'worktree *') {
            $candidate = $line.Substring(9).Trim()
            $candidateNorm = [System.IO.Path]::GetFullPath($candidate).TrimEnd('\').ToLowerInvariant()
            if ($candidateNorm -eq $needle) {
                return $true
            }
        }
    }
    return $false
}

function Test-LocalBranchExists {
    param([string]$Name)
    $res = Invoke-Git -GitArgs @('show-ref', '--verify', '--quiet', "refs/heads/$Name") -AllowFailure
    return $res.ExitCode -eq 0
}

function Test-RemoteBranchExists {
    param([string]$RemoteName, [string]$Name)
    $res = Invoke-Git -GitArgs @('ls-remote', '--exit-code', '--heads', $RemoteName, $Name) -AllowFailure
    return $res.ExitCode -eq 0
}

function Get-SanitizedFolderName {
    param([string]$Name)
    $san = $Name -replace '[\\/]+', '__'
    $san = $san -replace '[^A-Za-z0-9._-]', '_'
    $san = $san -replace '_{3,}', '__'
    return $san.Trim('_')
}

$repoRoot = Get-RepoRoot
Set-Location $repoRoot

Write-Host "[plan] repo root: $repoRoot"
Write-Host "[plan] branch: $Branch"
Write-Host "[plan] base: $Base"
Write-Host "[plan] remote: $Remote"
Write-Host "[plan] worktrees root: $WorktreesRoot"
Write-Host "[plan] push enabled: $($Push.IsPresent)"
Write-Host "[plan] force branch-exists bypass: $($Force.IsPresent)"

Ensure-CleanWorkingTree

Write-Host '[do] Fetching remote refs...'
Invoke-Git -GitArgs @('fetch', $Remote, '--prune') | Out-Null

if (-not (Test-RefExists -Ref 'refs/heads/main')) {
    Fail-Exit -Code 2 -Message 'Local branch "main" does not exist. Create it first before starting a slice.'
}
if (-not (Test-RefExists -Ref "refs/remotes/$Remote/main")) {
    Fail-Exit -Code 2 -Message "Remote tracking ref '$Remote/main' not found after fetch."
}

$mainDivergence = Get-AheadBehindCount -LeftRef 'main' -RightRef "$Remote/main"
if ($mainDivergence.Ahead -gt 0) {
    Fail-Exit -Code 2 -Message (("Local main is ahead of {0}/main by {1} commit(s). " +
        "Do not start a new slice until main is repaired/synced. " +
        "Tip: inspect with 'git log --oneline {0}/main..main'.") -f $Remote, $mainDivergence.Ahead)
}

Write-Host '[do] Resolving the worktree that owns local main...'
$mainWorktreePath = Get-WorktreePathForBranch -BranchName 'main'
if ([string]::IsNullOrWhiteSpace($mainWorktreePath)) {
    Fail-Exit -Code 2 -Message "Could not locate a worktree path for local branch 'main'."
}
Write-Host "[do] Main branch worktree: $mainWorktreePath"
Ensure-CleanWorkingTreeAtPath -Path $mainWorktreePath

Write-Host '[do] Fast-forward pulling main in its owning worktree...'
$pull = Invoke-Git -GitArgs @('pull', '--ff-only', $Remote, 'main') -WorkingDirectory $mainWorktreePath -AllowFailure
if ($pull.ExitCode -ne 0) {
    Fail-Exit -Code 2 -Message "main cannot fast-forward cleanly. Resolve main first.`n$($pull.Output)"
}
$mainPostPull = Get-AheadBehindCount -LeftRef 'main' -RightRef "$Remote/main"
if ($mainPostPull.Ahead -ne 0 -or $mainPostPull.Behind -ne 0) {
    Fail-Exit -Code 2 -Message (("main is not aligned to {0}/main after FF pull (ahead={1}, behind={2}). " +
        "Resolve this before creating a worktree.") -f $Remote, $mainPostPull.Ahead, $mainPostPull.Behind)
}
Write-Host "[ok] local main synced to $Remote/main"

$rootFull = [System.IO.Path]::GetFullPath((Join-Path $repoRoot $WorktreesRoot))
$mainOriginPath = Join-Path $rootFull 'main_origin'

if (Test-Path $mainOriginPath) {
    if (-not (Test-WorktreePathRegistered -Path $mainOriginPath)) {
        Fail-Exit -Code 2 -Message "Path exists but is not a registered git worktree: $mainOriginPath"
    }
    Ensure-CleanWorkingTreeAtPath -Path $mainOriginPath
    Write-Host "[do] Syncing main_origin worktree to $Remote/main..."
    $syncMainOrigin = Invoke-Git -GitArgs @('checkout', '--detach', "$Remote/main") -WorkingDirectory $mainOriginPath -AllowFailure
    if ($syncMainOrigin.ExitCode -ne 0) {
        Fail-Exit -Code 2 -Message "Failed to sync main_origin worktree.`n$($syncMainOrigin.Output)"
    }
} else {
    New-Item -ItemType Directory -Force -Path $rootFull | Out-Null
    Write-Host "[do] Creating main_origin worktree at: $mainOriginPath"
    $addMainOrigin = Invoke-Git -GitArgs @('worktree', 'add', '--detach', $mainOriginPath, "$Remote/main") -AllowFailure
    if ($addMainOrigin.ExitCode -ne 0) {
        Fail-Exit -Code 3 -Message "Failed to create main_origin worktree.`n$($addMainOrigin.Output)"
    }
}

$mainOriginDivergence = Get-AheadBehindCount -LeftRef 'HEAD' -RightRef "refs/remotes/$Remote/main" -WorkingDirectory $mainOriginPath
if ($mainOriginDivergence.Ahead -ne 0 -or $mainOriginDivergence.Behind -ne 0) {
    Fail-Exit -Code 2 -Message (("main_origin is not aligned to {0}/main (ahead={1}, behind={2}). " +
        "Resolve this before creating a worktree.") -f $Remote, $mainOriginDivergence.Ahead, $mainOriginDivergence.Behind)
}
Write-Host "[ok] main_origin synced to $Remote/main"

if (-not (Test-RefExists -Ref $Base)) {
    Fail-Exit -Code 2 -Message "Base ref '$Base' not found."
}

$localExists = Test-LocalBranchExists -Name $Branch
$remoteExists = Test-RemoteBranchExists -RemoteName $Remote -Name $Branch
if ($localExists -or $remoteExists) {
    if (-not $Force) {
        Fail-Exit -Code 2 -Message "Branch '$Branch' already exists (local=$localExists, remote=$remoteExists). Re-run with -Force only if this is intentional."
    }
    Write-Warning "Branch '$Branch' already exists (local=$localExists, remote=$remoteExists). Continuing due to -Force."
}

$folder = Get-SanitizedFolderName -Name $Branch
$targetPath = Join-Path $rootFull $folder

if (Test-Path $targetPath) {
    Fail-Exit -Code 2 -Message "Target worktree path already exists: $targetPath"
}

if ($PSCmdlet.ShouldProcess($targetPath, "Create worktree branch '$Branch' from '$Base'")) {
    New-Item -ItemType Directory -Force -Path $rootFull | Out-Null

    Write-Host "[do] Creating worktree at: $targetPath"
    $add = Invoke-Git -GitArgs @('worktree', 'add', '-b', $Branch, $targetPath, $Base) -AllowFailure
    if ($add.ExitCode -ne 0) {
        Fail-Exit -Code 3 -Message "Failed to add worktree.`n$($add.Output)"
    }

    $meta = [PSCustomObject]@{
        branch = $Branch
        base = $Base
        created_at = (Get-Date).ToString('o')
        repo_root = $repoRoot
        remote = $Remote
    }

    try {
        $metaPath = Join-Path $targetPath '.physicslab_worktree.json'
        $meta | ConvertTo-Json -Depth 4 | Set-Content -Encoding utf8 $metaPath

        # Keep worktree metadata local without polluting git status.
        $excludePath = Join-Path $targetPath '.git\info\exclude'
        if (Test-Path $excludePath) {
            $excludeText = Get-Content -Raw $excludePath
            if ($excludeText -notmatch '(^|\r?\n)\.physicslab_worktree\.json(\r?\n|$)') {
                Add-Content -Encoding utf8 $excludePath "`n.physicslab_worktree.json`n"
            }
        }
    }
    catch {
        Fail-Exit -Code 4 -Message "Worktree created but metadata write failed: $($_.Exception.Message)"
    }

    if ($Push) {
        Write-Host "[do] Pushing branch and setting upstream..."
        $pushRes = Invoke-Git -GitArgs @('push', '-u', $Remote, $Branch) -WorkingDirectory $targetPath -AllowFailure
        if ($pushRes.ExitCode -ne 0) {
            Fail-Exit -Code 3 -Message "Failed to push branch '$Branch'.`n$($pushRes.Output)"
        }
    } else {
        Write-Host '[note] Branch remains local-only (no push requested).'
    }

    Write-Host '[next] Run these commands:'
    Write-Host "  cd \"$targetPath\""
    Write-Host '  git status'
    Write-Host "  git log $Base..HEAD --oneline"
}

exit 0
