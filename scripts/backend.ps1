param([ValidateSet('test','package','run')][string]$Action='test')
$ErrorActionPreference='Stop'
$projectRoot=Split-Path -Parent $PSScriptRoot
$jdkRoot=Get-ChildItem -LiteralPath (Join-Path $projectRoot '.cache\toolchains\jdk21') -Directory | Select-Object -First 1 -ExpandProperty FullName
$maven=Join-Path $env:USERPROFILE '.codex\tools\apache-maven-3.9.9\bin\mvn.cmd'
if (-not (Test-Path -LiteralPath $maven)) { $maven=(Get-Command mvn -ErrorAction Stop).Source }
$settings=Get-Content -LiteralPath (Join-Path $projectRoot 'data\backend-local\connection.json') -Raw | ConvertFrom-Json
$env:JAVA_HOME=$jdkRoot
$env:PATH="$jdkRoot\bin;$env:PATH"
$env:BWP_DB_URL="jdbc:mysql://127.0.0.1:$($settings.port)/bwp_aide?connectionTimeZone=UTC&forceConnectionTimeZoneToSession=true&allowPublicKeyRetrieval=true&sslMode=DISABLED"
$env:BWP_DB_USER='bwp_dev'
$env:BWP_DB_PASSWORD=$settings.dev_password
$env:BWP_COLLECTOR_TOKEN=$settings.collector_token
$env:BWP_SCOPE_KEY='local-development'
$env:BWP_STORAGE_ROOT=Join-Path $projectRoot 'data\server-images'
$env:BWP_TEST_DB_URL="jdbc:mysql://127.0.0.1:$($settings.port)/bwp_stage3_test_local?connectionTimeZone=UTC&forceConnectionTimeZoneToSession=true&allowPublicKeyRetrieval=true&sslMode=DISABLED"
$env:BWP_TEST_DB_USER='bwp_test'
$env:BWP_TEST_DB_PASSWORD=$settings.test_password
$arguments=@('-B','-ntp','-f',(Join-Path $projectRoot 'backend\pom.xml'),"-Dmaven.repo.local=$(Join-Path $projectRoot '.cache\m2')")
switch ($Action) {
    'test' { $arguments+='verify' }
    'package' { $arguments+='package'; $arguments+='-DskipTests' }
    'run' { $arguments+='spring-boot:run' }
}
& $maven @arguments
exit $LASTEXITCODE
