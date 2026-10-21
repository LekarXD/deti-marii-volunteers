from datetime import timedelta
import hashlib,json
from uuid import UUID
from sqlalchemy import select,text
from app.core.auth import authz_guard,load_background_staff_authorization,lock_background_authorizations
from app.core.clock import utcnow
from app.core.errors import ApiError
from app.core.models import User
from app.core.audit import audit
from app.core.idempotency import begin_command,finish_command
from app.worker.queue import enqueue_job
from .rule_models import SignalRuleSettings,RuleSignal
from .rule_schemas import SignalThresholds,SignalRulesView,RuleSignalView
from .rule_sources import PERMISSIONS,collect
DEFAULTS=SignalThresholds().model_dump()

def require_manage(p):
    if not p.has_permission('followups.manage'):raise ApiError(403,'permission_denied','Для настройки правил нужен доступ к сопровождению всего фонда.')
async def settings(db,foundation_id,lock=False):
    if lock:await db.execute(text('SELECT pg_advisory_xact_lock(:key)'),{'key':int.from_bytes(hashlib.sha256(f'signal-rules:{foundation_id}'.encode()).digest()[:8],'big',signed=True)})
    query=select(SignalRuleSettings).where(SignalRuleSettings.foundation_id==foundation_id)
    return await db.scalar((query.with_for_update() if lock else query).execution_options(populate_existing=True))
def view(p,row):return SignalRulesView(thresholds=row.thresholds if row else DEFAULTS,defaults=DEFAULTS,version=row.version if row else 0,can_manage=p.has_permission('followups.manage'),last_run_at=row.last_run_at if row else None,next_run_at=row.next_run_at if row else None,last_result={name:(value if name not in PERMISSIONS or p.has_permission(PERMISSIONS[name]) else {'state':'unknown','reason':'source_permission_required'}) for name,value in row.last_result.items()} if row else {})
async def queue(db,row):enqueue_job(db,row.foundation_id,'followups.rules',dict(version=row.version,scheduled_for=row.next_run_at.isoformat()),available_at=row.next_run_at)
async def mutate(db,p,body,key,operation):
    try:
        await authz_guard(db,p);require_manage(p);row=await settings(db,p.foundation_id,True)
        name='followups.rules.'+operation;replay=await begin_command(db,p,name,key,body.model_dump(mode='json'))
        if replay is not None:await db.commit();return replay
        if body.expected_version!=(row.version if row else 0):raise ApiError(409,'version_conflict','Правила изменились. Обновите данные.',current_version=row.version if row else 0)
        if not row:row=SignalRuleSettings(foundation_id=p.foundation_id,thresholds=DEFAULTS.copy(),owner_user_id=p.user_id,version=0,next_run_at=utcnow());db.add(row)
        row.thresholds=body.thresholds.model_dump() if operation=='save' else DEFAULTS.copy() if operation=='reset' else row.thresholds
        row.owner_user_id=p.user_id;row.version+=1;row.next_run_at=utcnow();await queue(db,row);await db.flush()
        audit(db,p,name,'signal_rules',p.foundation_id,('thresholds','version'));value=view(p,row).model_dump(mode='json');await finish_command(db,p,name,key,value);await db.commit();return value
    except BaseException:await db.rollback();raise

def allowed(p,row,manage=False):return p.has_permission('followups.manage' if manage else 'followups.read','group',row.group_id) and p.has_permission(PERMISSIONS[row.rule])
def signal_view(p,row):return RuleSignalView(id=row.id,rule=row.rule,title=row.title,details={key:value for key,value in row.details.items() if key!='href'},state=row.state,version=row.version,observed_at=row.observed_at,can_manage=allowed(p,row,True),href=row.details.get('href','/fund/signals'))
async def evaluate(db,foundation_id,row,authority,context):
    now=utcnow();result={}
    await context.fence(db)
    if authority is None or not authority.has_permission('followups.manage'):
        result={'state':'blocked','reason':'owner_access_revoked'}
    else:
        for rule,permission in PERMISSIONS.items():
            if not authority.has_permission(permission):result[rule]=dict(state='unknown',reason='source_permission_required');continue
            observations,outcome=await collect(db,foundation_id,rule,row.thresholds[rule],now);result[rule]=outcome
            previous=(await db.scalars(select(RuleSignal).where(RuleSignal.foundation_id==foundation_id,RuleSignal.rule==rule).with_for_update())).all();by_id={x.entity_id:x for x in previous};matched=set()
            user_ids={item['subject_user_id'] for item in observations}-{None}
            users={user.id:user.display_name for user in (await db.scalars(select(User).where(User.id.in_(user_ids),User.foundation_id==foundation_id,User.account_state=='active'))).all()} if user_ids else {}
            for item in observations:
                if item['subject_user_id']:
                    if item['subject_user_id'] not in users:outcome['unknown']+=1;outcome['matched']-=1;continue
                    item['title']=item['title']+': '+users[item['subject_user_id']]
                source_hash=hashlib.sha256(json.dumps({key:value for key,value in item['details'].items() if key!='days'},sort_keys=True,separators=(',',':')).encode()).hexdigest();matched.add(item['entity_id']);signal=by_id.get(item['entity_id'])
                if signal is None:signal=RuleSignal(foundation_id=foundation_id,settings_version=row.version,source_hash=source_hash,**item);db.add(signal)
                else:
                    if signal.source_hash!=source_hash or signal.state=='resolved':signal.version+=1;signal.state='open'
                    if signal.state=='dismissed' and signal.source_hash==source_hash and 'decision_reason' in signal.details:item['details']['decision_reason']=signal.details['decision_reason']
                    signal.source_hash=source_hash;signal.settings_version=row.version
                    for key,value in item.items():setattr(signal,key,value)
                    signal.observed_at=signal.updated_at=now
            if outcome['state']=='evaluated' and not outcome['unknown']:
                for signal in previous:
                    if signal.entity_id not in matched and signal.state=='open':signal.state='resolved';signal.version+=1;signal.updated_at=now
    row.last_run_at=now;row.last_result=result;row.next_run_at=now+timedelta(hours=1);await queue(db,row);await context.fence(db);await db.flush();return result
