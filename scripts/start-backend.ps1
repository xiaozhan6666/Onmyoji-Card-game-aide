$ErrorActionPreference='Stop'
$projectRoot=Split-Path -Parent $PSScriptRoot
$stateRoot=Join-Path $projectRoot 'data\backend-local'
$settings=Get-Content -LiteralPath (Join-Path $stateRoot 'connection.json') -Raw | ConvertFrom-Json
$jdkRoot=Get-ChildItem -LiteralPath (Join-Path $projectRoot '.cache\toolchains\jdk21') -Directory | Select-Object -First 1 -ExpandProperty FullName
$jar=Join-Path $projectRoot 'backend\target\bwp-backend-0.1.0.jar'
if (-not (Test-Path -LiteralPath $jar)) { throw 'Run scripts/backend.ps1 package first.' }
$pidPath=Join-Path $stateRoot 'backend.pid'
if (Test-Path -LiteralPath $pidPath) {
    $existingPid=[int](Get-Content -LiteralPath $pidPath -Raw).Trim()
    $existing=Get-CimInstance Win32_Process -Filter "ProcessId=$existingPid"
    if ($existing -and $existing.CommandLine.Contains($jar)) { Write-Output 'Backend already running on 127.0.0.1:18080'; exit 0 }
}
$tcp=New-Object System.Net.Sockets.TcpClient
try { $tcp.Connect('127.0.0.1',18080); throw 'Port 18080 is already in use.' }
catch [System.Net.Sockets.SocketException] { }
finally { $tcp.Dispose() }
$env:BWP_DB_URL="jdbc:mysql://127.0.0.1:$($settings.port)/bwp_aide?connectionTimeZone=UTC&forceConnectionTimeZoneToSession=true&allowPublicKeyRetrieval=true&sslMode=DISABLED"
$env:BWP_DB_USER='bwp_dev'; $env:BWP_DB_PASSWORD=$settings.dev_password
$env:BWP_COLLECTOR_TOKEN=$settings.collector_token; $env:BWP_SCOPE_KEY='local-development'
$env:BWP_STORAGE_ROOT=Join-Path $projectRoot 'data\server-images'
$env:BWP_BIND_ADDRESS='127.0.0.1'; $env:BWP_PORT='18080'
$process=Start-Process -FilePath (Join-Path $jdkRoot 'bin\java.exe') -ArgumentList @('-Xms64m','-Xmx256m','-jar',"`"$jar`"") -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $stateRoot 'backend.log') -RedirectStandardError (Join-Path $stateRoot 'backend-error.log')
$process.Id | Set-Content -LiteralPath $pidPath -Encoding ASCII
$ready=$false
for($attempt=0;$attempt -lt 40;$attempt++) {
    if($process.HasExited) { throw 'Backend exited; inspect data/backend-local/backend.log' }
    try {
        $result=Invoke-RestMethod -Uri 'http://127.0.0.1:18080/api/health' -TimeoutSec 1
        if($result.status -eq 'ok') { $ready=$true; break }
    } catch { }
    Start-Sleep -Milliseconds 500
}
if(-not $ready) { throw 'Backend not ready; inspect data/backend-local/backend.log' }
Write-Output 'Backend ready: http://127.0.0.1:18080/api/health'
