import asyncio
import hashlib
import io
from PIL import Image, UnidentifiedImageError
from uuid import UUID, uuid4
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.auth import Principal, get_principal, authz_guard
from app.core.audit import audit
from app.core.db import get_db
from app.core.config import get_settings
from app.core.paths import public_path
from app.core.errors import ApiError
from app.core.models import MediaAsset
from app.core.rate_limit import rate_limit
from app.modules.assets.service import require_asset, asset_path, asset_content
router = APIRouter(prefix="/api/v1/assets", tags=["assets"])
validation_admission=asyncio.Semaphore(2)

def verify_file(path,asset,policy):
    try:
        data=path.read_bytes()
        if len(data)!=asset.expected_size or hashlib.sha256(data).hexdigest()!=asset.checksum:
            return False
        signatures={"image/png":b"\x89PNG\r\n\x1a\n","image/jpeg":b"\xff\xd8\xff","image/webp":b"RIFF","application/pdf":b"%PDF-"}
        if policy:
            if not policy.validate(data,asset.content_type):
                return False
        elif asset.content_type not in signatures or not data.startswith(signatures[asset.content_type]):
            return False
        if asset.content_type.startswith("image/"):
            with Image.open(io.BytesIO(data)) as image:
                expected={"image/png":"PNG","image/jpeg":"JPEG","image/webp":"WEBP"}[asset.content_type]
                if image.width*image.height>25_000_000 or image.format!=expected:
                    return False
                image.verify()
            with Image.open(io.BytesIO(data)) as image:
                image.load()
        return True
    except (OSError,ValueError,KeyError,UnidentifiedImageError,Image.DecompressionBombError):
        return False

class UploadIntent(BaseModel):
    content_type: str
    expected_size: int = Field(gt=0)
    checksum: str = Field(pattern="^[a-f0-9]{64}$")

class AssetView(BaseModel):
    id: UUID
    state: str
    received_size: int
    expected_size: int
    content_type: str
    upload_url: str

def view(asset):
    return {"id": str(asset.id), "state": asset.state, "received_size": asset.received_size, "expected_size": asset.expected_size, "content_type": asset.content_type, "upload_url": public_path(f"/api/v1/assets/{asset.id}/upload")}

@router.post("/upload-intents", operation_id="asset_upload_intent", response_model=AssetView)
async def intent(body: UploadIntent, principal: Principal = Depends(get_principal), db: AsyncSession = Depends(get_db)):
    # Anonymous sessions are free to mint, so they would make any per-owner disk budget meaningless.
    if not principal.user_id:
        raise ApiError(403, "verified_account_required", "Войдите в подтверждённый аккаунт")
    if body.content_type not in ("image/png", "image/jpeg", "image/webp", "application/pdf") or body.expected_size > get_settings().max_asset_bytes:
        raise ApiError(422, "unsupported_asset", "Допустимы PNG, JPEG, WebP и PDF в пределах лимита")
    await authz_guard(db, principal)
    await rate_limit(db, principal.actor_id, "asset.intent", limit=60, seconds=3600)
    pending = await db.scalar(select(func.coalesce(func.sum(MediaAsset.expected_size), 0)).where(MediaAsset.owner_user_id == principal.user_id, MediaAsset.purpose == "generic", MediaAsset.state == "uploading"))
    if pending + body.expected_size > 10 * get_settings().max_asset_bytes:
        await db.commit()
        raise ApiError(429, "upload_quota_exceeded", "Завершите начатые загрузки, прежде чем добавлять новые файлы", retryable=True)
    asset = MediaAsset(foundation_id=principal.foundation_id, owner_user_id=principal.user_id, owner_registration_id=principal.registration_id, storage_key=uuid4().hex, content_type=body.content_type, expected_size=body.expected_size, checksum=body.checksum)
    db.add(asset)
    await db.flush()
    audit(db, principal, "asset.intent", "asset", asset.id)
    await db.commit()
    return view(asset)

@router.patch("/{asset_id}/upload", operation_id="asset_upload_chunk", response_model=AssetView)
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

@router.post("/{asset_id}/complete-upload", operation_id="asset_upload_complete", response_model=AssetView)
async def complete_upload(asset_id: UUID, principal: Principal = Depends(get_principal), db: AsyncSession = Depends(get_db)):
    await authz_guard(db, principal)
    asset = await require_asset(db, principal, asset_id, ready=False)
    await db.refresh(asset, with_for_update=True)
    if asset.state in ("ready","processing"):
        return view(asset)
    if asset.state != "uploading":
        raise ApiError(409,"upload_closed","Загрузка закрыта")
    path = asset_path(asset)
    if asset.received_size != asset.expected_size or not path.exists():
        raise ApiError(409, "upload_incomplete", "Файл загружен не полностью")
    policy = None
    if asset.purpose != "generic":
        from app.modules.assets.registry import authorize_bound_asset
        policy=await authorize_bound_asset(db,principal,asset)
    try:
        await asyncio.wait_for(validation_admission.acquire(),timeout=1)
    except TimeoutError:
        raise ApiError(503,"asset_validation_busy","Проверка файлов занята. Повторите попытку",retryable=True)
    try:
        valid=await asyncio.to_thread(verify_file,path,asset,policy)
    finally:
        validation_admission.release()
    if not valid:
        asset.state="rejected"
        await db.commit()
        raise ApiError(422,"asset_validation_failed","Файл не прошёл проверку")
    if policy and policy.processor_kind:
        from app.worker.queue import enqueue_job
        job=enqueue_job(db,principal.foundation_id,policy.processor_kind,{"asset_id":str(asset.id),"resource_type":asset.resource_type,"resource_id":str(asset.resource_id),"source_checksum":asset.checksum})
        asset.processing_job_id=job.id
        asset.state="processing"
    else:
        asset.state = "ready"
    audit(db, principal, "asset.complete", "asset", asset.id, ("state",))
    await db.commit()
    return view(asset)

@router.get("/{asset_id}/status", operation_id="asset_status", response_model=AssetView)
async def status(asset_id: UUID, principal: Principal = Depends(get_principal), db: AsyncSession = Depends(get_db)):
    return view(await require_asset(db, principal, asset_id, ready=False))

@router.get("/{asset_id}/content", operation_id="asset_content")
async def content(asset_id: UUID, principal: Principal = Depends(get_principal), db: AsyncSession = Depends(get_db)):
    return await asset_content(db, await require_asset(db, principal, asset_id))
