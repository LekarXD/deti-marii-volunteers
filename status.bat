@echo off
powershell -NoProfile -Command "Write-Host 'Статус сервисов проекта «Опора»:' -ForegroundColor Yellow; docker compose --env-file infra/.env -f infra/compose.yaml ps"
pause
