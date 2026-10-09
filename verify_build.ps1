$ErrorActionPreference = 'Stop'
$appRoot = $PSScriptRoot
$checkFile = Join-Path $appRoot ('build-check-' + [guid]::NewGuid().ToString() + '.txt')
$previousPath = $env:PATH
$previousQtPlatform = $env:QT_QPA_PLATFORM
try {
    $env:PATH = "$env:SystemRoot\System32;$env:SystemRoot"
    $env:QT_QPA_PLATFORM = 'offscreen'
    $checkProcess = Start-Process -FilePath (Join-Path $appRoot 'dist-v6\Kotoba\Kotoba.exe') -ArgumentList @('--smoke-test', ('"' + $checkFile + '"')) -WindowStyle Hidden -PassThru
    if (-not $checkProcess.WaitForExit(20000)) {
        Stop-Process -Id $checkProcess.Id
        throw 'The packaged app did not finish its startup check.'
    }
    if ($checkProcess.ExitCode -ne 0 -or -not (Test-Path -LiteralPath $checkFile)) {
        throw 'The packaged app failed to load its UI and inference dependencies.'
    }
    Get-Content -LiteralPath $checkFile
} finally {
    $env:PATH = $previousPath
    $env:QT_QPA_PLATFORM = $previousQtPlatform
    if (Test-Path -LiteralPath $checkFile) { Remove-Item -LiteralPath $checkFile }
}
