from sqlalchemy import select,or_,false
from app.core.errors import ApiError
from app.modules.participants.models import ParticipantGroup
from .schemas import ReportScopeView

def allowed(authority,permission,scope_type,scope_id):
    return authority is not None and authority.has_permission(permission,scope_type,scope_id)
async def authorize_scope(db,authority,foundation_id,scope_type,scope_id,permission='reports.read'):
    if scope_type not in ('foundation','group') or (scope_type=='group')!=(scope_id is not None):raise ApiError(422,'invalid_report_scope','Укажите область отчёта')
    if not allowed(authority,permission,scope_type,scope_id):raise ApiError(403,'report_scope_denied','Нет доступа к этой области отчётов')
    label='Весь фонд'
    if scope_type=='group':
        group=await db.scalar(select(ParticipantGroup).where(ParticipantGroup.id==scope_id,ParticipantGroup.foundation_id==foundation_id))
        if group is None:raise ApiError(404,'report_group_not_found','Группа не найдена')
        label=group.title
    return ReportScopeView(scope_type=scope_type,scope_id=scope_id,label=label,can_write=allowed(authority,'reports.write',scope_type,scope_id),can_export=allowed(authority,'reports.export',scope_type,scope_id))
async def scope_options(db,principal):
    values=[]
    if allowed(principal,'reports.read','foundation',None):values.append(await authorize_scope(db,principal,principal.foundation_id,'foundation',None))
    groups=(await db.scalars(select(ParticipantGroup).where(ParticipantGroup.foundation_id==principal.foundation_id).order_by(ParticipantGroup.title,ParticipantGroup.id))).all()
    for group in groups:
        if allowed(principal,'reports.read','group',group.id):values.append(await authorize_scope(db,principal,principal.foundation_id,'group',group.id))
    return values

def report_filter(model,principal,permission='reports.read'):
    if principal.has_permission(permission):return model.foundation_id==principal.foundation_id
    groups=[scope_id for name,kind,scope_id in principal.grants if name==permission and kind=='group']
    return (model.foundation_id==principal.foundation_id)&(model.scope_type=='group')&model.scope_id.in_(groups) if groups else false()
