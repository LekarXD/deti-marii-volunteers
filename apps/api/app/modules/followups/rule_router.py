from uuid import UUID
from fastapi import APIRouter,Depends,Header
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.auth import Principal,get_principal,authz_guard
from app.core.db import get_db
from app.core.errors import ApiError
from app.core.audit import audit
from app.core.idempotency import begin_command,finish_command
from .rule_schemas import SignalRulesInput,SignalRulesVersionInput,SignalRulesView,RuleSignalView,RuleSignalDecision
from .rule_models import RuleSignal
from . import rules
from .service import scope
router=APIRouter()
@router.get('/coord/followups/rules',response_model=SignalRulesView,operation_id='followup_rules')
async def read_rules(db:AsyncSession=Depends(get_db),p:Principal=Depends(get_principal)):
    await authz_guard(db,p);rules.require_manage(p);return rules.view(p,await rules.settings(db,p.foundation_id))
@router.post('/coord/followups/rules',response_model=SignalRulesView,operation_id='followup_rules_save')
async def save_rules(body:SignalRulesInput,db:AsyncSession=Depends(get_db),p:Principal=Depends(get_principal),key:str|None=Header(default=None,alias='Idempotency-Key')):return await rules.mutate(db,p,body,key,'save')
@router.post('/coord/followups/rules/reset',response_model=SignalRulesView,operation_id='followup_rules_reset')
async def reset_rules(body:SignalRulesVersionInput,db:AsyncSession=Depends(get_db),p:Principal=Depends(get_principal),key:str|None=Header(default=None,alias='Idempotency-Key')):return await rules.mutate(db,p,body,key,'reset')
@router.post('/coord/followups/rules/evaluate',response_model=SignalRulesView,operation_id='followup_rules_evaluate')
async def scan_rules(body:SignalRulesVersionInput,db:AsyncSession=Depends(get_db),p:Principal=Depends(get_principal),key:str|None=Header(default=None,alias='Idempotency-Key')):return await rules.mutate(db,p,body,key,'evaluate')
@router.get('/coord/followups/rule-signals',response_model=list[RuleSignalView],operation_id='followup_rule_signals')
async def signals(db:AsyncSession=Depends(get_db),p:Principal=Depends(get_principal)):
    await authz_guard(db,p)
    if not any(name=='followups.read' for name,_,_ in p.grants):raise ApiError(403,'permission_denied','Нет доступа к сопровождению.')
    permitted=[name for name,permission in rules.PERMISSIONS.items() if p.has_permission(permission)]
    rows=(await db.scalars(select(RuleSignal).where(RuleSignal.foundation_id==p.foundation_id,RuleSignal.state=='open',RuleSignal.rule.in_(permitted),scope(p,'followups.read',RuleSignal)).order_by(RuleSignal.observed_at.desc(),RuleSignal.id).limit(500))).all()
    return [rules.signal_view(p,row) for row in rows if rules.allowed(p,row)]
@router.post('/coord/followups/rule-signals/{id}/dismiss',response_model=RuleSignalView,operation_id='followup_rule_signal_dismiss')
async def dismiss(id:UUID,body:RuleSignalDecision,db:AsyncSession=Depends(get_db),p:Principal=Depends(get_principal),key:str|None=Header(default=None,alias='Idempotency-Key')):
    try:
        await authz_guard(db,p);row=await db.scalar(select(RuleSignal).where(RuleSignal.id==id,RuleSignal.foundation_id==p.foundation_id).with_for_update())
        if row is None or not rules.allowed(p,row) or not rules.allowed(p,row,True):raise ApiError(404,'signal_not_found','Сигнал недоступен.')
        name='followups.rule.dismiss:'+str(id);replay=await begin_command(db,p,name,key,body.model_dump(mode='json'))
        if replay is not None:await db.commit();return replay
        if row.version!=body.expected_version:raise ApiError(409,'version_conflict','Сигнал изменился.',current_version=row.version)
        if len(body.reason.strip())<3:raise ApiError(422,'reason_required','Укажите причину закрытия сигнала.')
        row.state='dismissed';row.version+=1;row.details={**row.details,'decision_reason':body.reason.strip()};audit(db,p,name,'rule_signal',id,('state','decision_reason'));value=rules.signal_view(p,row).model_dump(mode='json');await finish_command(db,p,name,key,value);await db.commit();return value
    except BaseException:await db.rollback();raise
