#Requires -Version 5.1
<#
.SYNOPSIS
    Create the GitHub repository, push main, and lock it down so that every
    change must arrive as a Pull Request with green required checks.

.DESCRIPTION
    Idempotent helper. It performs:
      1. create the repository (from governance/repository-settings.json)
      2. set the remote over SSH and push main + tags
      3. apply the repository settings and topics
      4. protect `main` (from governance/branch-protection.json):
         - PR required, required status checks must be green and up to date
         - dismiss stale reviews, require conversation resolution, linear history
         - no force push, no deletion, rebase-merge only

    The token is only used for the REST calls and is never written to disk,
    never put on a command line, and never added to .git/config: the push goes
    over SSH, so the clone needs a working SSH key for the owner account.

    Requires a token with the `repo` scope: pass -Token or set
    $env:GH_TOKEN / $env:GITHUB_TOKEN. -DryRun needs no token at all.

    NOTE: run this AFTER an initial `git init && git add -A && git commit -s`.

.EXAMPLE
    $env:GH_TOKEN = 'ghp_xxx'
    powershell -ExecutionPolicy Bypass -File tools/create-github-repo.ps1 -Owner cadywang

.EXAMPLE
    # Dry run: print the exact API calls without touching GitHub
    powershell -ExecutionPolicy Bypass -File tools/create-github-repo.ps1 -Owner cadywang -DryRun
#>
[CmdletBinding()]
param(
  [Parameter(Mandatory = $true)][string]$Owner,
  [string]$Repo = 'codex-agent-team',
  [string]$Token = '',
  [string]$BaseBranch = 'main',
  [switch]$Private,
  [switch]$DryRun,
  [switch]$Release
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

$api = 'https://api.github.com'
$root = Split-Path -Parent $PSScriptRoot
Push-Location $root
try {
  if (-not $Token) {
    $Token = if ($env:GH_TOKEN) { $env:GH_TOKEN } elseif ($env:GITHUB_TOKEN) { $env:GITHUB_TOKEN } else { '' }
  }
  if (-not $Token -and -not $DryRun) {
    $sec = Read-Host -Prompt 'GitHub token (repo scope)' -AsSecureString
    $Token = [Runtime.InteropServices.Marshal]::PtrToStringUni(
      [Runtime.InteropServices.Marshal]::SecureStringToGlobalAllocUnicode($sec))
  }

  $headers = @{
    'Authorization' = "Bearer $Token"
    'Accept'        = 'application/vnd.github+json'
    'X-GitHub-Api-Version' = '2022-11-28'
    'User-Agent'    = 'codex-agent-team-bootstrap'
  }

  function Invoke-Gh([string]$Method, [string]$Uri, $Body, [switch]$AllowMissing) {
    if ($DryRun) {
      Write-Host "[dry-run] $Method $Uri"
      if ($null -ne $Body) { Write-Host ($Body | ConvertTo-Json -Depth 8) }
      return $null
    }
    try {
      if ($null -ne $Body) {
        $json = $Body | ConvertTo-Json -Depth 10
        return Invoke-RestMethod -Method $Method -Uri $Uri -Headers $headers `
                 -ContentType 'application/json' -Body ([System.Text.Encoding]::UTF8.GetBytes($json))
      }
      return Invoke-RestMethod -Method $Method -Uri $Uri -Headers $headers
    } catch {
      $status = 0
      try { $status = [int]$_.Exception.Response.StatusCode.value__ } catch {}
      if ($AllowMissing -and $status -eq 404) { return $null }
      $detail = ''
      try { $sr = New-Object System.IO.StreamReader($_.Exception.Response.GetResponseStream()); $detail = $sr.ReadToEnd() } catch {}
      Write-Host "FAILED: $Method $Uri (HTTP $status)"
      Write-Host $detail
      throw
    }
  }

  function Invoke-Git([string[]]$Arguments) {
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
      $output = & git @Arguments 2>&1
      return @{ code = $LASTEXITCODE; output = (($output | ForEach-Object { "$_" }) -join "`n") }
    } finally {
      $ErrorActionPreference = $previous
    }
  }

  # ---- 0. sanity: local git repo with at least one commit ----
  if (-not (Get-Command git -ErrorAction SilentlyContinue)) { throw 'git not found on PATH' }
  & git rev-parse --is-inside-work-tree *> $null
  if ($LASTEXITCODE -ne 0) { throw "not a git work tree: $root" }
  & git rev-parse HEAD *> $null
  if ($LASTEXITCODE -ne 0) { throw 'no commit yet; run: git add -A && git commit -s' }

  $settings = Get-Content -Raw -Encoding UTF8 "$root\governance\repository-settings.json" | ConvertFrom-Json
  $protection = Get-Content -Raw -Encoding UTF8 "$root\governance\branch-protection.json" | ConvertFrom-Json

  # GitHub refuses the squash/merge title fields while that strategy is off,
  # so only send the ones the enabled strategies can carry.
  $settingsKeys = @($settings.PSObject.Properties.Name)
  $mergeFields = @{}
  if ($settings.allow_squash_merge) {
    foreach ($k in @('squash_merge_commit_message', 'squash_merge_commit_title')) {
      if ($settingsKeys -contains $k) { $mergeFields[$k] = $settings.$k }
    }
  }
  if ($settings.allow_merge_commit -and $settingsKeys -contains 'merge_commit_title') {
    $mergeFields['merge_commit_title'] = $settings.merge_commit_title
  }

  # ---- 1. create repository ----
  Write-Host '==> repository'
  $existing = Invoke-Gh 'GET' "$api/repos/$Owner/$Repo" $null -AllowMissing
  $repoBody = @{
    description            = $settings.description
    has_issues             = [bool]$settings.has_issues
    has_projects           = [bool]$settings.has_projects
    has_wiki               = [bool]$settings.has_wiki
    has_discussions        = [bool]$settings.has_discussions
    allow_squash_merge     = [bool]$settings.allow_squash_merge
    allow_merge_commit     = [bool]$settings.allow_merge_commit
    allow_rebase_merge     = [bool]$settings.allow_rebase_merge
    allow_auto_merge       = [bool]$settings.allow_auto_merge
    delete_branch_on_merge = [bool]$settings.delete_branch_on_merge
  }
  if ($existing) {
    Write-Host "    exists: $($existing.full_name) (visibility private=$($existing.private))"
    try {
      Invoke-Gh 'PATCH' "$api/repos/$Owner/$Repo" ($repoBody + $mergeFields) | Out-Null
      Write-Host '    settings updated'
    } catch {
      Write-Host '    warn: this token cannot update repository settings (needs administration:write)'
      Write-Host '          continuing - settings are cosmetic, the push and the branch rules are not'
    }
  } else {
    # POST /users/{owner}/repos does not exist (it answers 404). A repository
    # is created for the authenticated account with POST /user/repos, and for
    # an organisation with POST /orgs/{owner}/repos.
    $me = $null
    if (-not $DryRun) { $me = Invoke-Gh 'GET' "$api/user" $null }
    $login = if ($me) { $me.login } else { '' }
    $createUri = if ($login -and $login -ne $Owner) {
      "$api/orgs/$Owner/repos"
    } else {
      "$api/user/repos"
    }

    $create = @{
      name               = $Repo
      description        = $settings.description
      homepage           = $settings.homepage
      private            = [bool]($Private -or $settings.private)
      has_issues         = [bool]$settings.has_issues
      has_projects       = [bool]$settings.has_projects
      has_wiki           = [bool]$settings.has_wiki
      has_discussions    = [bool]$settings.has_discussions
      auto_init          = $false
      allow_squash_merge = [bool]$settings.allow_squash_merge
      allow_merge_commit = [bool]$settings.allow_merge_commit
      allow_rebase_merge = [bool]$settings.allow_rebase_merge
      delete_branch_on_merge = [bool]$settings.delete_branch_on_merge
    }
    try {
      Invoke-Gh 'POST' $createUri ($create + $mergeFields) | Out-Null
    } catch {
      Write-Host ''
      Write-Host '  The repository could not be created with this token.'
      Write-Host '  Some fine-grained tokens are not allowed to create repositories at all.'
      Write-Host '  In that case: create it once at https://github.com/new and leave it'
      Write-Host '  EMPTY (no README, no .gitignore, no licence), then re-run this script.'
      Write-Host '  It will detect the existing repository, push, and protect main.'
      throw
    }
    Write-Host "    created $Owner/$Repo"
  }

  if ($settings.topics) {
    if (-not $DryRun) {
      try {
        $t = @{ names = @($settings.topics) } | ConvertTo-Json
        Invoke-WebRequest -Method Put -Uri "$api/repos/$Owner/$Repo/topics" -Headers $headers `
          -ContentType 'application/vnd.github.mercy-preview+json' -Body ([Text.Encoding]::UTF8.GetBytes($t)) `
          -UseBasicParsing | Out-Null
        Write-Host '    topics set'
      } catch { Write-Host '    warn: cannot set topics with this token; continuing' }
    } else { Write-Host '[dry-run] PUT topics' }
  }

  # ---- 2. push over SSH (the token is never used here) ----
  Write-Host '==> push'
  $remoteUrl = "git@github.com:$Owner/$Repo.git"
  if (-not $DryRun) {
    $remotes = @(Invoke-Git @('remote')).output -split "`n"
    if ($remotes -contains 'origin') {
      Invoke-Git @('remote', 'set-url', 'origin', $remoteUrl) | Out-Null
    } else {
      Invoke-Git @('remote', 'add', 'origin', $remoteUrl) | Out-Null
    }
    Invoke-Git @('branch', '-M', $BaseBranch) | Out-Null
    $pushed = Invoke-Git @('push', '--quiet', '-u', 'origin', $BaseBranch)
    if ($pushed.code -ne 0) {
      Write-Host $pushed.output
      Write-Host '  The push was rejected. Two usual causes:'
      Write-Host '    - the local SSH key is not the owner account (git@github.com auth),'
      Write-Host '    - or the repository was created WITH an initial commit (README /'
      Write-Host '      .gitignore / licence ticked in the web form).'
      Write-Host '  For the second case, recreate it empty, or adopt the existing history:'
      Write-Host '      git pull --rebase origin main'
      Write-Host '      git push -u origin main'
      throw 'git push failed'
    }
    Invoke-Git @('push', '--quiet', '--tags') | Out-Null
    Write-Host "    pushed $BaseBranch (+tags) over SSH"
  } else { Write-Host "[dry-run] git remote set-url origin $remoteUrl && git push -u origin $BaseBranch --tags" }

  # ---- 3. branch protection ----
  Write-Host "==> protect $BaseBranch (PR + required checks)"
  $payload = @{
    required_status_checks = @{
      strict   = [bool]$protection.required_status_checks.strict
      contexts = @($protection.required_status_checks.contexts)
    }
    enforce_admins                  = [bool]$protection.enforce_admins
    required_pull_request_reviews   = @{
      dismiss_stale_reviews           = [bool]$protection.required_pull_request_reviews.dismiss_stale_reviews
      require_code_owner_reviews      = [bool]$protection.required_pull_request_reviews.require_code_owner_reviews
      required_approving_review_count = [int]$protection.required_pull_request_reviews.required_approving_review_count
      require_last_push_approval      = [bool]$protection.required_pull_request_reviews.require_last_push_approval
    }
    restrictions                    = $null
    required_linear_history         = [bool]$protection.required_linear_history
    allow_force_pushes              = [bool]$protection.allow_force_pushes
    allow_deletions                 = [bool]$protection.allow_deletions
    block_creations                 = [bool]$protection.block_creations
    required_conversation_resolution = [bool]$protection.required_conversation_resolution
    lock_branch                     = [bool]$protection.lock_branch
    allow_fork_syncing              = [bool]$protection.allow_fork_syncing
  }
  try {
    Invoke-Gh 'PUT' "$api/repos/$Owner/$Repo/branches/$BaseBranch/protection" $payload | Out-Null
  } catch {
    Write-Host ''
    Write-Host '  Branch protection was NOT applied, so main is still open for direct pushes.'
    Write-Host '  The token needs repository administration rights for this call:'
    Write-Host '    - classic token: the repo scope (you already own the repository)'
    Write-Host '    - fine-grained token: Contents=Read/Write and Administration=Read/Write'
    throw
  }

  # ---- 4. optional release ----
  if ($Release) {
    $described = Invoke-Git @('describe', '--tags', '--abbrev=0')
    $ver = if ($described.code -eq 0) { $described.output.Trim() } else { '' }
    if ($ver) {
      Write-Host "==> release $ver"
      Invoke-Gh 'POST' "$api/repos/$Owner/$Repo/releases" @{
        tag_name = $ver; name = $ver; generate_release_notes = $true; draft = $false; prerelease = $false
      } | Out-Null
    } else { Write-Host '    no tag found, skipping release' }
  }

  Write-Host ''
  Write-Host "Done. https://github.com/$Owner/$Repo"
  Write-Host "  - direct pushes to $BaseBranch are blocked for everyone (incl. admins)"
  Write-Host '  - every change needs a PR with the required checks green'
}
finally { Pop-Location }
