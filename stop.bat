@echo off
powershell -NoProfile -Command "Write-Host 'Остановка контейнеров проекта «Опора»...' -ForegroundColor Yellow; docker compose --env-file infra/.env -f infra/compose.yaml stop; Write-Host '==============================================' -ForegroundColor Green; Write-Host 'Проект остановлен. Все данные в базе сохранены!' -ForegroundColor Green; Write-Host '==============================================' -ForegroundColor Green"
pause
