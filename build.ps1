<#
.SYNOPSIS
  Windows wrapper around build.py.
.DESCRIPTION
  The packaging rules (which files ship, how keys.py is baked, how addons.xml is
  hashed) live in build.py only. Keeping a second implementation here meant the
  two could drift and produce different ZIPs, so this just calls the real one.
#>
param(
  [string]$BaseUrl = "http://127.0.0.1:8080",
  [string]$Output,
  [string]$Keys
)

$ErrorActionPreference = "Stop"
$script = Join-Path $PSScriptRoot "build.py"
$arguments = @($script, "--base-url", $BaseUrl)
if ($Output) { $arguments += @("--output", $Output) }
if ($Keys) { $arguments += @("--keys", $Keys) }

$python = (Get-Command py -ErrorAction SilentlyContinue)
if ($python) { & py -3 @arguments } else { & python @arguments }
if ($LASTEXITCODE -ne 0) { throw "build.py failed with exit code $LASTEXITCODE" }
