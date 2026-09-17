<#
.SYNOPSIS
  OCR every attached screenshot, newest first.
.DESCRIPTION
  Images in this conversation can no longer be rendered, so read them as text.
  Each photo is upscaled and contrast-stretched first, because OCR on a phone
  photo of a TV is much worse without it.
#>
param(
  [string]$Attachments = "$env:USERPROFILE\.t3\userdata\attachments",
  [int]$Count = 12
)

$ErrorActionPreference = "Stop"
$ffmpeg = Get-ChildItem "$env:LOCALAPPDATA\Microsoft\WinGet\Packages\Gyan.FFmpeg*" -Recurse -Filter ffmpeg.exe |
  Select-Object -First 1 -ExpandProperty FullName
$work = Join-Path $env:TEMP "grn-ocr"
New-Item -ItemType Directory -Force -Path $work | Out-Null

$shots = Get-ChildItem $Attachments -File |
  Where-Object { $_.Extension -match '^\.(jpg|jpeg|png)$' } |
  Sort-Object LastWriteTime -Descending | Select-Object -First $Count

foreach ($shot in $shots) {
  $prepared = Join-Path $work ($shot.BaseName.Substring([Math]::Max(0, $shot.BaseName.Length - 12)) + ".png")
  & $ffmpeg -hide_banner -loglevel error -y -i $shot.FullName `
    -vf "scale=iw*1.6:ih*1.6:flags=lanczos,eq=contrast=1.35:brightness=0.02,unsharp=5:5:1.0" `
    $prepared 2>$null
  Write-Output ("=" * 70)
  Write-Output ("FILE: " + $shot.Name + "   (" + $shot.LastWriteTime.ToString("HH:mm:ss") + ")")
  Write-Output ("-" * 70)
  try {
    & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "ocr.ps1") -Path $prepared
  } catch {
    Write-Output ("OCR failed: " + $_.Exception.Message)
  }
}
