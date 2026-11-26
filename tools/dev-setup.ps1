#Requires -Version 5.1
<#
.SYNOPSIS
    Configure a clone for contributing (Windows counterpart of dev-setup.sh).

.DESCRIPTION
    Turns on the two conventions this repository is maintained with:
      * format.signOff  -> every commit carries Signed-off-by: (DCO)
      * core.hooksPath  -> tools/git-hooks/commit-msg validates the message
    then runs the checker over the current history as a smoke test.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File tools/dev-setup.ps1
#>
Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $PSScriptRoot
Push-Location $root
try {
  & git rev-parse --is-inside-work-tree *> $null
  if ($LASTEXITCODE -ne 0) { throw 'dev-setup: not inside a git work tree' }

  & git config format.signOff true
  & git config core.hooksPath tools/git-hooks

  Write-Host ("format.signOff  = " + (& git config --get format.signOff))
  Write-Host ("core.hooksPath  = " + (& git config --get core.hooksPath))

  $py = $null
  foreach ($c in @('python3', 'python', 'py')) {
    $cmd = Get-Command $c -ErrorAction SilentlyContinue
    if ($cmd) {
      & $c -c 'import sys' *> $null
      if ($LASTEXITCODE -eq 0) { $py = $c; break }
    }
  }
  if ($py) {
    & $py tools/check-commits.py --all | Select-Object -Last 3
  } else {
    Write-Host 'dev-setup: python not found, skipping the history smoke test'
  }
  Write-Host 'dev-setup: done'
}
finally { Pop-Location }
