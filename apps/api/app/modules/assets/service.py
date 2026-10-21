from pathlib import Path
from fastapi.responses import FileResponse
from sqlalchemy import select
from app.core.config import get_settings
from app.core.errors import ApiError
from app.core.models import MediaAsset

def asset_path(asset):
    root = Path(get_settings().asset_root).resolve()
    path = root / asset.storage_key
    if path.parent != root:
        raise ApiError(404, "asset_not_found", "Файл не найден")
    return path

async def require_asset(db, principal, asset_id, ready=True):
    asset = await db.scalar(select(MediaAsset).where(MediaAsset.id == asset_id, MediaAsset.foundation_id == principal.foundation_id))
    if not asset:
        raise ApiError(404, "asset_not_found", "Файл не найден")
    if asset.access_permission:
        allowed = principal.has_permission(asset.access_permission)
    else:
        allowed = (principal.user_id is not None and asset.owner_user_id == principal.user_id) or (principal.registration_id is not None and asset.owner_registration_id == principal.registration_id) or principal.has_permission("assets.manage")
    if not allowed:
        raise ApiError(404, "asset_not_found", "Файл не найден")
    if ready and asset.state != "ready":
        raise ApiError(409, "asset_not_ready", "Файл ещё не готов")
    return asset

async def asset_content(db, asset):
    if asset.state != "ready" or not asset_path(asset).is_file():
        raise ApiError(404, "asset_unavailable", "Файл недоступен")
    return FileResponse(asset_path(asset), media_type=asset.content_type, filename=str(asset.id), headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})
