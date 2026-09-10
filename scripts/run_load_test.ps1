$ErrorActionPreference = 'Stop'
function Check-Exit { if ($LASTEXITCODE -ne 0) { throw "Load-test command failed: $LASTEXITCODE" } }
$loadRoot = Split-Path $PSScriptRoot -Parent
Set-Location $loadRoot
foreach ($loadName in @('azari-load-db', 'azari-load-backend', 'azari-load-frontend')) {
    $existing = docker ps -a --filter "name=^/$loadName$" --format '{{.Names}}'
    if ($existing) { throw "Existing test container $loadName; inspect it before starting another run." }
}
$existingNetwork = docker network ls --filter 'name=^azari-load-test$' --format '{{.Name}}'
if ($existingNetwork) { throw 'Test network already exists; inspect before reuse.' }
$loadDbPassword = [guid]::NewGuid().ToString('N')
$env:LOAD_JWT_SECRET = [guid]::NewGuid().ToString('N') + [guid]::NewGuid().ToString('N')
$env:LOAD_PASSWORD = 'Load-' + [guid]::NewGuid().ToString('N')
docker network create azari-load-test
Check-Exit
docker run -d --name azari-load-db --network azari-load-test --network-alias load-db --cpus 2 --memory 1g -e POSTGRES_DB=azari_load_test -e POSTGRES_USER=loadtest -e "POSTGRES_PASSWORD=$loadDbPassword" postgres:16-alpine
Check-Exit
for ($loadAttempt=0; $loadAttempt -lt 30; $loadAttempt++) {
    docker exec azari-load-db pg_isready -U loadtest -d azari_load_test
    if ($LASTEXITCODE -eq 0) { break }
    Start-Sleep -Seconds 1
}
Check-Exit
docker run -d --name azari-load-backend --network azari-load-test --cpus 2 --memory 1g -p 127.0.0.1:18100:8000 --mount "type=bind,source=$PSScriptRoot,target=/load,readonly" -e PYTHONPATH=/app -e "DATABASE_URL=postgresql+psycopg://loadtest:${loadDbPassword}@load-db:5432/azari_load_test" -e "JWT_SECRET=$env:LOAD_JWT_SECRET" -e "LOAD_PASSWORD=$env:LOAD_PASSWORD" -e ML_MODEL_DIR=/tmp/load-models -e AUTH_RATE_LIMIT_ATTEMPTS=5 -e AUTH_RATE_LIMIT_WINDOW_SECONDS=60 azari-accounting-backend:latest sh -c 'alembic -c /app/backend/alembic.ini upgrade 20260901_0010 && python -m backend.app.db.bootstrap && alembic -c /app/backend/alembic.ini upgrade head && python /load/seed_load_test.py && uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --no-access-log'
Check-Exit
docker run -d --name azari-load-frontend --network azari-load-test --cpus .5 --memory 128m -p 127.0.0.1:14173:80 azari-accounting-frontend:latest
Check-Exit
Write-Output 'Seeding 10,000 synthetic accounts; waiting for isolated backend readiness.'
for ($loadAttempt=0; $loadAttempt -lt 180; $loadAttempt++) {
    try {
        $response = Invoke-WebRequest -UseBasicParsing http://127.0.0.1:18100/api/v1/ready -TimeoutSec 2
        if ($response.StatusCode -eq 200) { break }
    } catch { }
    if ($loadAttempt % 15 -eq 0) { Write-Output "Waiting for seed: attempt $loadAttempt" }
    Start-Sleep -Seconds 2
}
if ($loadAttempt -eq 180) { throw 'Isolated backend did not become ready; inspect docker logs.' }
& "$loadRoot\.venv\Scripts\python.exe" scripts/run_load_test.py
Check-Exit
Remove-Item Env:LOAD_PASSWORD
Remove-Item Env:LOAD_JWT_SECRET
Write-Output 'Test complete. Containers retained for inspection; no live data was accessed.'
