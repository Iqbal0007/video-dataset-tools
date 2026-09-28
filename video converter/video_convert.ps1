[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [ValidateScript({ Test-Path -LiteralPath $_ -PathType Leaf })]
    [string]$InputPath,

    [ValidateRange(1, 240)]
    [int]$FrameRate = 30,

    [string]$OutputPath,

    [switch]$Force
)

$ffmpeg = Get-Command ffmpeg -ErrorAction SilentlyContinue
if (-not $ffmpeg) {
    throw "ffmpeg was not found on PATH. Install ffmpeg, then run this script again."
}

$inputFile = (Resolve-Path -LiteralPath $InputPath).Path
if (-not $OutputPath) {
    $OutputPath = [System.IO.Path]::ChangeExtension($inputFile, '.mp4')
}

$outputFile = [System.IO.Path]::GetFullPath($OutputPath)
if ((Test-Path -LiteralPath $outputFile) -and -not $Force) {
    throw "Output file already exists: $outputFile. Re-run with -Force to replace it."
}

# Raw H.264 has no timestamps, so supply the source frame rate explicitly.
& $ffmpeg.Source -hide_banner -y -framerate $FrameRate -i $inputFile `
    -c:v copy -movflags +faststart $outputFile

if ($LASTEXITCODE -ne 0) {
    throw "Conversion failed with ffmpeg exit code $LASTEXITCODE."
}

Write-Host "Created: $outputFile"
