@echo off
powershell -NoProfile -Command "Write-Host 'Запуск проекта «Опора»...' -ForegroundColor Yellow; docker compose --env-file infra/.env -f infra/compose.yaml up -d; Write-Host '==============================================' -ForegroundColor Green; Write-Host 'Проект успешно запущен! Откройте в браузере: http://127.0.0.1:8080' -ForegroundColor Green; Write-Host '==============================================' -ForegroundColor Green"
pause
