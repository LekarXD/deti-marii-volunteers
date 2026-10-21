from datetime import datetime
from uuid import UUID
from fastapi import APIRouter,Depends,Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.auth import Principal,get_principal,authz_guard
from app.core.db import get_db
from app.core.errors import ApiError
from .schemas import AdminAuditPageView
from .service import audit_page
router=APIRouter(prefix='/api/v1',tags=['admin'])

@router.get('/coord/admin/audit',response_model=AdminAuditPageView,operation_id='admin_audit_list')
async def audit_events(limit:int=Query(30,ge=1,le=100),cursor:str|None=Query(None,max_length=4096),from_at:datetime|None=None,until_at:datetime|None=None,command:str|None=Query(None,max_length=120),foundation_id:UUID|None=None,principal:Principal=Depends(get_principal),db:AsyncSession=Depends(get_db)):
    await authz_guard(db,principal)
    if not principal.has_permission('staff.manage'):raise ApiError(403,'permission_denied','Недостаточно прав для просмотра журнала фонда')
    if foundation_id is not None and foundation_id!=principal.foundation_id:raise ApiError(403,'foundation_scope_denied','Журнал другого фонда недоступен')
    return await audit_page(db,principal,limit=limit,cursor=cursor,from_at=from_at,until_at=until_at,command=command)
