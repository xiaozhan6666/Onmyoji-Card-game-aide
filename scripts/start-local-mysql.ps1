$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$mysqlRoot = Get-ChildItem -LiteralPath (Join-Path $projectRoot '.cache\toolchains\mysql84') -Directory | Select-Object -First 1 -ExpandProperty FullName
if (-not $mysqlRoot) { throw '缺少项目 MySQL 8.4，请先准备独立工具链。' }
$stateRoot = Join-Path $projectRoot 'data\backend-local'
$dbRoot = Join-Path $stateRoot 'mysql-data'
New-Item -ItemType Directory -Force -Path $stateRoot | Out-Null
$configPath = Join-Path $stateRoot 'connection.json'
if (-not (Test-Path -LiteralPath $configPath)) {
    function New-LocalSecret { return [Guid]::NewGuid().ToString('N') + [Guid]::NewGuid().ToString('N') }
    @{ port=33307; root_password=(New-LocalSecret); dev_password=(New-LocalSecret); test_password=(New-LocalSecret); collector_token=(New-LocalSecret) } |
        ConvertTo-Json | Set-Content -LiteralPath $configPath -Encoding UTF8
}
$settings = Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json
$pidPath = Join-Path $stateRoot 'mysqld.pid'
if (Test-Path -LiteralPath $pidPath) {
    $existingPid = [int](Get-Content -LiteralPath $pidPath -Raw).Trim()
    $existing = Get-Process -Id $existingPid -ErrorAction SilentlyContinue
    if ($existing -and $existing.Path -eq (Join-Path $mysqlRoot 'bin\mysqld.exe')) {
        Write-Output "项目 MySQL 已运行，端口 $($settings.port)"; exit 0
    }
}
$tcp = New-Object System.Net.Sockets.TcpClient
try { $tcp.Connect('127.0.0.1',[int]$settings.port); throw "端口 $($settings.port) 已被其他进程占用" }
catch [System.Net.Sockets.SocketException] { }
finally { $tcp.Dispose() }
if (-not (Test-Path -LiteralPath (Join-Path $dbRoot 'mysql'))) {
    if ((Test-Path -LiteralPath $dbRoot) -and (Get-ChildItem -LiteralPath $dbRoot -Force | Select-Object -First 1)) {
        throw '数据目录非空但未初始化；保留目录，请先检查初始化日志。'
    }
    & (Join-Path $mysqlRoot 'bin\mysqld.exe') --no-defaults --initialize-insecure "--basedir=$mysqlRoot" "--datadir=$dbRoot" --innodb-buffer-pool-size=67108864 "--log-error=$(Join-Path $stateRoot 'initialize.log')"
    if ($LASTEXITCODE -ne 0) { throw 'MySQL 初始化失败，请查看 data/backend-local/initialize.log' }
}
$initPath = Join-Path $stateRoot 'startup.sql'
@"
ALTER USER 'root'@'localhost' IDENTIFIED BY '$($settings.root_password)';
CREATE DATABASE IF NOT EXISTS bwp_aide CHARACTER SET utf8mb4;
CREATE DATABASE IF NOT EXISTS bwp_stage3_test_local CHARACTER SET utf8mb4;
CREATE USER IF NOT EXISTS 'bwp_dev'@'localhost' IDENTIFIED BY '$($settings.dev_password)';
CREATE USER IF NOT EXISTS 'bwp_test'@'localhost' IDENTIFIED BY '$($settings.test_password)';
GRANT ALL PRIVILEGES ON bwp_aide.* TO 'bwp_dev'@'localhost';
GRANT ALL PRIVILEGES ON bwp_stage3_test_local.* TO 'bwp_test'@'localhost';
"@ | Set-Content -LiteralPath $initPath -Encoding ASCII
$arguments = @('--no-defaults', "--basedir=`"$mysqlRoot`"", "--datadir=`"$dbRoot`"", '--bind-address=127.0.0.1', "--port=$($settings.port)", '--mysqlx=0', '--skip-log-bin', '--innodb-buffer-pool-size=134217728', "--pid-file=`"$pidPath`"", "--log-error=`"$(Join-Path $stateRoot 'mysql.log')`"", "--init-file=`"$initPath`"")
$server = Start-Process -FilePath (Join-Path $mysqlRoot 'bin\mysqld.exe') -ArgumentList $arguments -WindowStyle Hidden -PassThru
$oldPassword = $env:MYSQL_PWD
try {
    $env:MYSQL_PWD = $settings.root_password
    $ready = $false
    for ($attempt=0; $attempt -lt 40; $attempt++) {
        if ($server.HasExited) { throw '项目 MySQL 启动失败，请查看 mysql.log' }
        $ErrorActionPreference = 'Continue'
        $null = & (Join-Path $mysqlRoot 'bin\mysql.exe') --no-defaults --protocol=TCP -h 127.0.0.1 "-P$($settings.port)" -uroot --connect-timeout=1 -e 'SELECT 1' 2>$null
        $ErrorActionPreference = 'Stop'
        if ($LASTEXITCODE -eq 0) { $ready=$true; break }
        Start-Sleep -Milliseconds 500
    }
    if (-not $ready) { throw '项目 MySQL 尚未就绪，请查看 mysql.log' }
    Remove-Item -LiteralPath $initPath
    Write-Output "项目 MySQL 8.4 已启动：127.0.0.1:$($settings.port)。凭据保存在 data/backend-local/connection.json（不提交版本库）。"
} finally { $env:MYSQL_PWD=$oldPassword }
