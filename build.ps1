$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

function Invoke-Checked {
    param([string]$File, [string[]]$ArgumentList)
    & $File @ArgumentList
    if ($LASTEXITCODE -ne 0) { throw "$File exited with code $LASTEXITCODE" }
}

Invoke-Checked python @('-m', 'pip', 'install', 'pyinstaller==6.11.1', 'ruff==0.8.6')
Invoke-Checked python @('-m', 'ruff', 'check', '.')
Invoke-Checked python @('-m', 'unittest', 'discover', '-s', 'tests', '-v')
Invoke-Checked python @('-m', 'PyInstaller', '--noconfirm', '--clean', '--onefile', '--windowed', '--name', 'MusX-Space', 'app.py')
$process = Start-Process '.\dist\MusX-Space.exe' -ArgumentList '--smoke-test' -PassThru
if (-not $process.WaitForExit(30000)) {
    $process.Kill()
    throw 'The packaged application did not exit after the smoke test.'
}
if ($process.ExitCode -ne 0) { throw "Smoke test exited with code $($process.ExitCode)" }

$iscc = Join-Path ${env:ProgramFiles(x86)} 'Inno Setup 6\ISCC.exe'
Invoke-Checked $iscc @('installer\MusX.iss')
Copy-Item 'dist\MusX-Space.exe' release
$hashes = Get-ChildItem release -Filter '*.exe' | ForEach-Object {
    $hash = (Get-FileHash $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    "$hash  $($_.Name)"
}
$hashes | Set-Content release\SHA256SUMS.txt -Encoding ascii
