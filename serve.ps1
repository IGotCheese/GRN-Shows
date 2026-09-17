param([int]$Port = 8080)

$ErrorActionPreference = "Stop"
$dist = Join-Path $PSScriptRoot "dist"
if (-not (Test-Path -LiteralPath (Join-Path $dist "index.html"))) {
  & (Join-Path $PSScriptRoot "build.ps1") -BaseUrl "http://127.0.0.1:$Port"
}
Write-Host "Serving GRN Shows at http://127.0.0.1:$Port — press Ctrl+C to stop."
if (Get-Command python -ErrorAction SilentlyContinue) {
  python -m http.server $Port --directory $dist
} elseif (Get-Command py -ErrorAction SilentlyContinue) {
  py -3 -m http.server $Port --directory $dist
} else {
  throw "Python 3 is required to run the local web server."
}
