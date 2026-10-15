$ErrorActionPreference='Stop'
$projectRoot=Split-Path -Parent $PSScriptRoot
$stateRoot=Join-Path $projectRoot 'data\backend-local'
$jar=Join-Path $projectRoot 'backend\target\bwp-backend-0.1.0.jar'
$pidPath=Join-Path $stateRoot 'backend.pid'
if(Test-Path -LiteralPath $pidPath) {
    $backendPid=[int](Get-Content -LiteralPath $pidPath -Raw).Trim()
    $process=Get-CimInstance Win32_Process -Filter "ProcessId=$backendPid"
    if($process -and $process.CommandLine.Contains($jar)) {
        Stop-Process -Id $backendPid
        Write-Output 'Stopped this project backend.'
    }
}
$mysqlRoot=Get-ChildItem -LiteralPath (Join-Path $projectRoot '.cache\toolchains\mysql84') -Directory | Select-Object -First 1 -ExpandProperty FullName
$mysqlPidPath=Join-Path $stateRoot 'mysqld.pid'
if(Test-Path -LiteralPath $mysqlPidPath) {
    $mysqlPid=[int](Get-Content -LiteralPath $mysqlPidPath -Raw).Trim()
    $process=Get-CimInstance Win32_Process -Filter "ProcessId=$mysqlPid"
    if($process -and $process.ExecutablePath -eq (Join-Path $mysqlRoot 'bin\mysqld.exe') -and $process.CommandLine.Contains((Join-Path $stateRoot 'mysql-data'))) {
        $settings=Get-Content -LiteralPath (Join-Path $stateRoot 'connection.json') -Raw | ConvertFrom-Json
        $oldPassword=$env:MYSQL_PWD
        try {
            $env:MYSQL_PWD=$settings.root_password
            & (Join-Path $mysqlRoot 'bin\mysqladmin.exe') --no-defaults --protocol=TCP -h 127.0.0.1 "-P$($settings.port)" -uroot shutdown
            if($LASTEXITCODE -ne 0) { throw 'MySQL shutdown failed.' }
            Write-Output 'Stopped this project MySQL.'
        } finally { $env:MYSQL_PWD=$oldPassword }
    }
}
