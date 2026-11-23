param([ValidateSet('Start','Stop','Restart')][string]$Action='Start')
$ErrorActionPreference='Stop'
$partsRoot=(Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$partsPython=Join-Path $partsRoot '.venv\Scripts\python.exe'
$partsState=Join-Path $partsRoot 'instance'
$partsPidFile=Join-Path $partsState 'server.pid'
if (!(Test-Path -LiteralPath $partsPython)) { throw 'Create the .venv and install requirements first.' }
New-Item -ItemType Directory -Path $partsState -Force | Out-Null
if (Test-Path -LiteralPath $partsPidFile) {
    $partsPid=[int](Get-Content -LiteralPath $partsPidFile -Raw)
    $partsProcess=Get-Process -Id $partsPid -ErrorAction SilentlyContinue
    if ($partsProcess) {
        if ($partsProcess.Path -ne $partsPython) { throw 'PID file belongs to another process; refusing to stop it.' }
        $partsCommand=Get-CimInstance Win32_Process -Filter "ProcessId=$partsPid"
        if ($partsCommand.CommandLine -notmatch 'main\.py') { throw 'PID file does not identify the application launcher.' }
        if ($Action -eq 'Start') { Write-Output "DMTDB is already running (launcher PID $partsPid)."; exit 0 }
        # Windows venv Python launches the interpreter as a child process.
        $partsChildren=Get-CimInstance Win32_Process -Filter "ParentProcessId=$partsPid"
        foreach ($partsChild in $partsChildren) {
            if ($partsChild.Name -eq 'conhost.exe' -and $partsChild.ExecutablePath -eq (Join-Path $env:WINDIR 'system32\conhost.exe')) { continue }
            if ($partsChild.Name -ne 'python.exe' -or $partsChild.CommandLine -notmatch 'main\.py') {
                throw 'Unexpected launcher child; inspect before stopping.'
            }
        }
        foreach ($partsChild in $partsChildren | Where-Object Name -eq 'python.exe') { Stop-Process -Id $partsChild.ProcessId -ErrorAction SilentlyContinue }
        Stop-Process -Id $partsPid -ErrorAction SilentlyContinue
    }
}
if ($Action -eq 'Stop') { Write-Output 'Local DMTDB stopped.'; exit 0 }
$partsProcess=Start-Process -FilePath $partsPython -ArgumentList '-u','main.py' -WorkingDirectory $partsRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $partsState 'server.log') -RedirectStandardError (Join-Path $partsState 'server-error.log') -PassThru
Set-Content -LiteralPath $partsPidFile -Value $partsProcess.Id
Write-Output "Local DMTDB started (launcher PID $($partsProcess.Id)). See config.local.ini for the URL."
