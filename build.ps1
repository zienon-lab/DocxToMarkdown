[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$venvPython = Join-Path $projectRoot '.venv\Scripts\python.exe'
$outputExe = Join-Path $projectRoot 'dist\DocxToMarkdown.exe'
$finalExe = Join-Path $projectRoot 'DocxToMarkdown.exe'

Set-Location -LiteralPath $projectRoot

if (-not (Test-Path -LiteralPath $venvPython)) {
    py -3.12 -m venv (Join-Path $projectRoot '.venv')
}

& $venvPython -m pip install --disable-pip-version-check -r (Join-Path $projectRoot 'requirements.txt')
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }

$pandocCommand = Get-Command pandoc.exe -ErrorAction SilentlyContinue
if ($pandocCommand) {
    $pandocPath = $pandocCommand.Source
} else {
    $pandocPath = Join-Path $env:ProgramFiles 'Pandoc\pandoc.exe'
}
if (-not (Test-Path -LiteralPath $pandocPath)) {
    throw 'pandoc.exe was not found; the standalone build cannot continue.'
}

& $venvPython -m unittest discover -s tests -v
if ($LASTEXITCODE -ne 0) { throw 'Automated tests failed; packaging stopped.' }

& $venvPython -m PyInstaller `
    --noconfirm `
    --clean `
    --noconsole `
    --onefile `
    --noupx `
    --name DocxToMarkdown `
    --version-file (Join-Path $projectRoot 'version_info.txt') `
    --add-binary "$pandocPath;tools" `
    --paths $projectRoot `
    (Join-Path $projectRoot 'app\main.py')
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller packaging failed.' }

if (-not (Test-Path -LiteralPath $outputExe)) {
    throw 'Packaging finished without producing dist\DocxToMarkdown.exe.'
}
Copy-Item -LiteralPath $outputExe -Destination $finalExe -Force

$file = Get-Item -LiteralPath $finalExe
Write-Host "Build succeeded: $($file.FullName)"
Write-Host "File size: $([math]::Round($file.Length / 1MB, 2)) MB"
