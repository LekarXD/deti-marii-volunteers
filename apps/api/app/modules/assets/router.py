import asyncio
import hashlib
import io
from PIL import Image, UnidentifiedImageError
from uuid import UUID, uuid4
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.auth import Principal, get_principal, authz_guard
from app.core.audit import audit
from app.core.db import get_db
from app.core.config import get_settings
from app.core.errors import ApiError
from app.core.models import MediaAsset
from app.modules.assets.service import require_asset, asset_path, asset_content
router = APIRouter(prefix="/api/v1/assets", tags=["assets"])
class UploadIntent(BaseModel):
    content_type: str
    expected_size: int = Field(gt=0)
    checksum: str = Field(pattern="^[a-f0-9]{64}$")

def view(asset):
    return {"id": str(asset.id), "state": asset.state, "received_size": asset.received_size, "expected_size": asset.expected_size, "content_type": asset.content_type, "upload_url": f"/api/v1/assets/{asset.id}/upload"}

@router.post("/upload-intents", operation_id="asset_upload_intent")
async def intent(body: UploadIntent, principal: Principal = Depends(get_principal), db: AsyncSession = Depends(get_db)):
    if body.content_type not in ("image/png", "image/jpeg", "image/webp", "application/pdf") or body.expected_size > get_settings().max_asset_bytes:
        raise ApiError(422, "unsupported_asset", "Допустимы PNG, JPEG, WebP и PDF в пределах лимита")
    asset = MediaAsset(foundation_id=principal.foundation_id, owner_user_id=principal.user_id, owner_registration_id=principal.registration_id, storage_key=uuid4().hex, content_type=body.content_type, expected_size=body.expected_size, checksum=body.checksum)
    db.add(asset)
    await db.flush()
    audit(db, principal, "asset.intent", "asset", asset.id)
    await db.commit()
    return view(asset)

@router.patch("/{asset_id}/upload", operation_id="asset_upload_chunk")
async def upload(asset_id: UUID, request: Request, principal: Principal = Depends(get_principal), db: AsyncSession = Depends(get_db)):
    await authz_guard(db, principal)
    asset = await require_asset(db, principal, asset_id, ready=False)
    await db.refresh(asset, with_for_update=True)
    if asset.state != "uploading":
        raise ApiError(409, "upload_closed", "Загрузка завершена")
    try:
        offset = int(request.headers.get("x-upload-offset", "-1"))
    except ValueError:
        offset = -1
    if offset != asset.received_size:
        raise ApiError(409, "upload_offset_conflict", "Повторите загрузку с подтверждённого смещения", current_version=asset.received_size)
    chunks, size = [], 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > min(1024*1024, asset.expected_size-offset):
            raise ApiError(413, "chunk_too_large", "Часть файла превышает лимит")
        chunks.append(chunk)
    path = asset_path(asset)
    def write():
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        mode = "r+b" if path.exists() else "w+b"
        with path.open(mode) as handle:
            handle.truncate(offset)
            handle.seek(offset)
            handle.write(b"".join(chunks))
            handle.flush()
    await asyncio.to_thread(write)
    asset.received_size += size
    await db.commit()
    return view(asset)

@router.post("/{asset_id}/complete-upload", operation_id="asset_upload_complete")
async def complete_upload(asset_id: UUID, principal: Principal = Depends(get_principal), db: AsyncSession = Depends(get_db)):
    await authz_guard(db, principal)
    asset = await require_asset(db, principal, asset_id, ready=False)
    await db.refresh(asset, with_for_update=True)
    if asset.state == "ready":
        return view(asset)
    path = asset_path(asset)
    if asset.received_size != asset.expected_size or not path.exists():
        raise ApiError(409, "upload_incomplete", "Файл загружен не полностью")
    data = await asyncio.to_thread(path.read_bytes)
    signatures = {"image/png": b"\x89PNG\r\n\x1a\n", "image/jpeg": b"\xff\xd8\xff", "application/pdf": b"%PDF-", "image/webp": b"RIFF"}
    if len(data) != asset.expected_size or hashlib.sha256(data).hexdigest() != asset.checksum or not data.startswith(signatures[asset.content_type]):
        asset.state = "rejected"
        await db.commit()
        raise ApiError(422, "asset_validation_failed", "Файл не прошёл проверку")
    if asset.content_type.startswith("image/"):
        def validate_image():
            try:
                with Image.open(io.BytesIO(data)) as image:
                    if image.width * image.height > 25_000_000:
                        return False
                    expected_format = {"image/png":"PNG", "image/jpeg":"JPEG", "image/webp":"WEBP"}[asset.content_type]
                    if image.format != expected_format:
                        return False
                    image.verify()
                return True
            except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
                return False
        if not await asyncio.to_thread(validate_image):
            asset.state = "rejected"
            await db.commit()
            raise ApiError(422, "asset_validation_failed", "Изображение не прошло проверку")
    asset.state = "ready"
    audit(db, principal, "asset.complete", "asset", asset.id, ("state",))
    await db.commit()
    return view(asset)

@router.get("/{asset_id}/status", operation_id="asset_status")
async def status(asset_id: UUID, principal: Principal = Depends(get_principal), db: AsyncSession = Depends(get_db)):
    return view(await require_asset(db, principal, asset_id, ready=False))

@router.get("/{asset_id}/content", operation_id="asset_content")
async def content(asset_id: UUID, principal: Principal = Depends(get_principal), db: AsyncSession = Depends(get_db)):
    return await asset_content(db, await require_asset(db, principal, asset_id))
