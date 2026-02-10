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

    if ($WorkingDirectory) {
        $output = & git -C $WorkingDirectory @GitArgs 2>&1
    } else {
        $output = & git @GitArgs 2>&1
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

function Test-RefExists {
    param([string]$Ref)
    $res = Invoke-Git -GitArgs @('rev-parse', '--verify', $Ref) -AllowFailure
    return $res.ExitCode -eq 0
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

Write-Host '[do] Switching to local main...'
Invoke-Git -GitArgs @('checkout', 'main') | Out-Null
Ensure-CleanWorkingTree

Write-Host '[do] Fast-forward pulling main...'
$pull = Invoke-Git -GitArgs @('pull', '--ff-only', $Remote, 'main') -AllowFailure
if ($pull.ExitCode -ne 0) {
    Fail-Exit -Code 2 -Message "main cannot fast-forward cleanly. Resolve main first.`n$($pull.Output)"
}

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

$rootFull = [System.IO.Path]::GetFullPath((Join-Path $repoRoot $WorktreesRoot))
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
