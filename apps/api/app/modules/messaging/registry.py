"""Trusted source resolvers rebuild scheduled notices under current domain authorization."""
import importlib
SOURCES={}
LOCK_SUBJECTS={}
def register_notice_source(kind,validate,*,lock_subjects=None):
    if not kind or len(kind)>80 or not callable(validate):raise ValueError('invalid_notice_source')
    if kind in SOURCES and SOURCES[kind] is not validate:raise ValueError('duplicate_notice_source')
    if len(SOURCES)>=16 and kind not in SOURCES:raise ValueError('notice_source_budget')
    SOURCES[kind]=validate
    LOCK_SUBJECTS[kind]=lock_subjects

def notice_source(kind):
    for module in ('app.modules.reporting.notifications','app.modules.studio.summary_notifications','app.modules.dobro.notifications'):
        try:importlib.import_module(module)
        except ModuleNotFoundError as error:
            if error.name not in (module,module.rsplit('.',1)[0]):raise
    return SOURCES.get(kind)

async def prepare_notice_source_locks(db,outbox,payload):
    source=payload.get('source')
    if not isinstance(source,dict) or not isinstance(source.get('kind'),str):return
    resolver=notice_source(source['kind'])
    if resolver is None:return
    transaction=db.sync_session.get_transaction()
    markers=db.info.setdefault('notice_source_locks',{})
    if transaction is not None and markers.get(outbox.id) is transaction:return
    lookup=LOCK_SUBJECTS.get(source['kind'])
    if lookup is not None:
        from app.core.auth import lock_background_authorizations
        subjects=await lookup(db,outbox,source)
        if subjects:await lock_background_authorizations(db,outbox.foundation_id,subjects)
    markers[outbox.id]=db.sync_session.get_transaction()
