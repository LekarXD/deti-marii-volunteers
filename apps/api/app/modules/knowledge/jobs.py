import asyncio
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from app.core.auth import resolve_principal
from app.core.models import MediaAsset, Session
from app.integrations.ai.models import AIRun
from app.integrations.ai.service import execute_run
from app.worker.registry import register_handler
from .models import KnowledgeChunk, KnowledgeSource, MentorRun, SourceVersion

async def index_source(db,context):
    source=await db.scalar(select(KnowledgeSource).where(KnowledgeSource.id==UUID(context.payload['source_id']),KnowledgeSource.foundation_id==context.foundation_id).with_for_update())
    if source is None or source.archived or str(source.current_version_id)!=context.payload['source_version_id'] or source.index_generation!=context.payload['generation']:
        return {'state':'stale'}
    version=await db.get(SourceVersion,source.current_version_id)
    await context.fence(db)
    # Stable paragraph windows retain exact source text. Index rows are immutable.
    text=version.body.strip()
    chunks=[text[start:start+1200] for start in range(0,len(text),1200)]
    for position,part in enumerate(chunks):
        await db.execute(insert(KnowledgeChunk).values(source_version_id=version.id,position=position,text=part).on_conflict_do_nothing())
    source.index_state='ready'
    source.index_error=None
    return {'state':'ready','chunks':len(chunks),'source_version_id':str(version.id)}

async def ingest_pdf(db,context):
    from app.modules.assets.service import asset_path
    source=await db.scalar(select(KnowledgeSource).where(KnowledgeSource.id==UUID(context.payload['source_id']),KnowledgeSource.foundation_id==context.foundation_id).with_for_update())
    if source is None or source.draft_version!=context.payload['draft_version'] or str(source.asset_id)!=context.payload['asset_id']:
        return {'state':'stale'}
    asset=await db.scalar(select(MediaAsset).where(MediaAsset.id==source.asset_id,MediaAsset.foundation_id==context.foundation_id,MediaAsset.state=='ready',MediaAsset.content_type=='application/pdf'))
    if asset is None:
        source.index_state,source.index_error='failed','asset_unavailable'
        return {'state':'failed','error_code':source.index_error}
    def extract():
        from pypdf import PdfReader
        reader=PdfReader(asset_path(asset))
        if len(reader.pages)>200:raise ValueError('page_budget')
        return '\n\n'.join((page.extract_text() or '')[:30000] for page in reader.pages)[:200000]
    try:
        text=await asyncio.wait_for(asyncio.to_thread(extract),timeout=30)
        await context.fence(db)
        if len(text.strip())<10:
            source.index_state,source.index_error='failed','pdf_without_text'
        else:
            source.draft_body=text
            source.draft_version+=1
            source.reviewed_version=None
            source.index_state,source.index_error='unpublished',None
    except asyncio.CancelledError:raise
    except Exception:
        await context.fence(db)
        source.index_state,source.index_error='failed','pdf_ingestion_failed'
    return {'state':source.index_state,'error_code':source.index_error}

async def generate_ai(db,context):
    result=await execute_run(db,context)
    run=await db.get(AIRun,UUID(context.payload['run_id']))
    if run is None:return result
    from app.integrations.ai.contracts import TASKS
    hook=TASKS[run.task].on_complete
    if hook is not None and run.state not in {'queued','calling'}:
        await context.fence(db)
        await hook(db,run,context)
    if run.task!='mentor':return result
    items=(await db.scalars(select(MentorRun).where(MentorRun.ai_run_id==run.id).with_for_update())).all()
    session=await db.get(Session,run.request_session_id)
    if session is None:return result
    principal=await resolve_principal(db,session)
    from .service import create_question,fragments_by_id
    await context.fence(db)
    for item in items:
        item.state=run.state
        if run.state=='succeeded':
            output=run.output or {}
            citation_ids=output.get('citation_ids',[])
            visible=await fragments_by_id(db,principal,citation_ids)
            valid=bool(visible) and len(visible)==len(citation_ids) and set(citation_ids).issubset(set(run.source_refs))
            if output.get('unknown') or not valid:
                item.state='unknown'
                if not item.question_id:
                    question=await create_question(db,principal,item.question)
                    item.question_id=question.id
            else:
                item.state,item.answer,item.citation_ids='answered',output.get('answer'),citation_ids
    return result

register_handler('knowledge.index',index_source,lease_seconds=120,heartbeat_seconds=20,timeout_seconds=60)
register_handler('knowledge.ingest',ingest_pdf,lease_seconds=120,heartbeat_seconds=20,timeout_seconds=60)
register_handler('ai.generate',generate_ai,lease_seconds=150,heartbeat_seconds=20,timeout_seconds=120)
