"""Internal resource-bound upload purposes, registered by trusted domain code."""
import importlib
from dataclasses import dataclass
from typing import Awaitable, Callable
from uuid import UUID, uuid4
from app.core.errors import ApiError
from app.core.models import MediaAsset

@dataclass(frozen=True)
class AssetPurpose:
    content_types: frozenset[str]
    max_bytes: int
    authorize: Callable[..., Awaitable[None]]
    validate: Callable[[bytes,str],bool]
    processor_kind: str | None

PURPOSES: dict[str, AssetPurpose]={}

def register_asset_purpose(name,*,content_types,max_bytes,authorize,validate,processor_kind=None):
    if name=="generic" or not name or not 0<max_bytes<=500*1024*1024 or not callable(authorize) or not callable(validate):
        raise ValueError("invalid_asset_purpose")
    if name in PURPOSES:
        current=PURPOSES[name]
        if current.authorize is not authorize:
            raise ValueError("duplicate_asset_purpose")
        return
    if len(PURPOSES)>=32:
        raise ValueError("purpose_budget_exceeded")
    PURPOSES[name]=AssetPurpose(frozenset(content_types),max_bytes,authorize,validate,processor_kind)

def load_asset_extensions():
    for name in ("app.modules.studio.assets","app.modules.profile.assets","app.modules.recordings.assets"):
        try:
            importlib.import_module(name)
        except ModuleNotFoundError as exc:
            if exc.name not in (name,name.rsplit(".",1)[0]):
                raise

def purpose_for(name):
    load_asset_extensions()
    purpose=PURPOSES.get(name)
    if purpose is None:
        raise ApiError(503,"asset_processor_unavailable","Обработка этого вида файлов пока недоступна",retryable=True)
    return purpose

async def authorize_bound_asset(db,principal,asset):
    purpose=purpose_for(asset.purpose)
    if asset.foundation_id!=principal.foundation_id:
        raise ApiError(404,"asset_not_found","Файл не найден")
    await purpose.authorize(db,principal,asset.resource_type,asset.resource_id)
    return purpose

async def create_upload_intent(db,principal,*,content_type,expected_size,checksum,purpose,resource_type,resource_id):
    """Python-only interface: the public generic intent DTO never accepts these fields."""
    policy=purpose_for(purpose)
    if content_type not in policy.content_types or not 0<expected_size<=policy.max_bytes or len(checksum)!=64 or any(c not in '0123456789abcdef' for c in checksum) or not resource_type or resource_id is None:
        raise ApiError(422,"unsupported_asset","Проверьте формат и размер файла")
    await policy.authorize(db,principal,resource_type,resource_id)
    asset=MediaAsset(foundation_id=principal.foundation_id,owner_user_id=principal.user_id,owner_registration_id=principal.registration_id,storage_key=uuid4().hex,content_type=content_type,expected_size=expected_size,checksum=checksum,purpose=purpose,resource_type=resource_type,resource_id=resource_id)
    db.add(asset)
    await db.flush()
    return asset

async def create_generated_asset(db,principal,*,content_type,data,purpose,resource_type,resource_id):
    """One private asset lifecycle for generated documents; caller owns its resource.

    Call context.fence(db) immediately before invoking from a durable worker.
    The source file is private and unreferenced until the caller commits the
    resource update and job completion. An aborted transaction may leave an
    unreferenced private file, never a published document.
    """
    import asyncio
    import hashlib
    import os
    from app.core.auth import authz_guard
    from app.modules.assets.service import asset_path
    await authz_guard(db,principal)
    policy=purpose_for(purpose)
    if not isinstance(data,bytes) or not 0<len(data)<=policy.max_bytes or content_type not in policy.content_types:
        raise ApiError(422,"generated_asset_invalid","Проверьте формат и размер документа")
    if not await asyncio.to_thread(policy.validate,data,content_type):
        raise ApiError(422,"generated_asset_invalid","Документ не прошёл проверку")
    asset=await create_upload_intent(db,principal,content_type=content_type,expected_size=len(data),checksum=hashlib.sha256(data).hexdigest(),purpose=purpose,resource_type=resource_type,resource_id=resource_id)
    path=asset_path(asset)
    def write():
        path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        temporary=path.with_name(path.name+"."+uuid4().hex+".tmp")
        try:
            with temporary.open("xb") as output:
                os.chmod(temporary,0o600)
                output.write(data)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary,path)
        finally:
            temporary.unlink(missing_ok=True)
    await asyncio.to_thread(write)
    asset.received_size=len(data)
    asset.state="ready"
    await db.flush()
    return asset
