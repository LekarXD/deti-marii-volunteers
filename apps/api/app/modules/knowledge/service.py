from datetime import datetime, timezone
from uuid import UUID
from sqlalchemy import func, select
from app.core.auth import Principal
from app.core.errors import ApiError
from app.core.models import PermissionGrant, StaffMembership, User
from app.worker.queue import enqueue_job
from app.integrations.ai.models import AIRun
from app.integrations.ai.service import enqueue_ai_run
from .models import ApprovedAnswer, KnowledgeChunk, KnowledgeQuestion, KnowledgeSource, MentorRun, SourceVersion


def permission(principal,name):
    if not principal.has_permission(name):
        raise ApiError(403,'permission_denied','Недостаточно прав для базы знаний')

def owner_scope(principal,model):
    if principal.user_id:
        return model.user_id==principal.user_id
    if principal.registration_id:
        return model.registration_id==principal.registration_id
    raise ApiError(403,'owner_required','Нужна личная сессия')

def check_version(actual,expected):
    if actual!=expected:
        raise ApiError(409,'version_conflict','Материал изменён. Обновите страницу',current_version=actual)

async def source(db,principal,source_id,lock=False):
    value=await db.scalar(select(KnowledgeSource).where(KnowledgeSource.id==source_id,KnowledgeSource.foundation_id==principal.foundation_id).with_for_update() if lock else select(KnowledgeSource).where(KnowledgeSource.id==source_id,KnowledgeSource.foundation_id==principal.foundation_id))
    if value is None:
        raise ApiError(404,'source_not_found','Источник не найден')
    return value

def can_edit(principal,value):
    return principal.has_permission('knowledge.manage') or principal.has_permission('knowledge.write') and principal.user_id==value.owner_user_id

def source_view(principal,value):
    return dict(id=value.id,title=value.title,kind=value.kind,body=value.draft_body,visibility=value.draft_visibility,version=value.draft_version,reviewed_version=value.reviewed_version,current_version_id=value.current_version_id,archived=value.archived,index_state=value.index_state,index_error=value.index_error,can_edit=can_edit(principal,value))

async def source_list(db,principal):
    permission(principal,'knowledge.read')
    items=(await db.scalars(select(KnowledgeSource).where(KnowledgeSource.foundation_id==principal.foundation_id).order_by(KnowledgeSource.updated_at.desc()).limit(200))).all()
    return [source_view(principal,item) for item in items]

async def imported_lesson(db,principal,version_id):
    from app.modules.learning.models import LearningRelease, LearningTrack, LessonBlock, LessonVersion
    permission(principal,'learning.read')
    releases=(await db.scalars(select(LearningRelease).join(LearningTrack,LearningTrack.current_release_id==LearningRelease.id).where(LearningTrack.foundation_id==principal.foundation_id,LearningTrack.archived.is_(False)))).all()
    if not any(str(version_id) in release.lesson_version_ids for release in releases):
        raise ApiError(404,'lesson_not_published','Опубликованный урок не найден')
    blocks=(await db.scalars(select(LessonBlock).where(LessonBlock.lesson_version_id==version_id).order_by(LessonBlock.position))).all()
    lines=[]
    def text_parts(value):
        if isinstance(value,str):
            lines.append(value)
        elif isinstance(value,list):
            for part in value:text_parts(part)
        elif isinstance(value,dict):
            for key in ['title','text','intro','items']:
                if key in value:text_parts(value[key])
    for block in blocks:
        if block.content.get('type') not in {'quiz','video','file'}:
            text_parts(block.content)
    return '\n\n'.join(lines)[:200000]

async def create_source(db,principal,body):
    permission(principal,'knowledge.write')
    content=body.body
    if body.lesson_version_id:
        content=await imported_lesson(db,principal,body.lesson_version_id)
    if body.asset_id:
        from app.modules.assets.service import require_asset
        asset=await require_asset(db,principal,body.asset_id)
        if asset.content_type!='application/pdf':
            raise ApiError(422,'unsupported_source','Для импорта нужен PDF с текстом')
    value=KnowledgeSource(foundation_id=principal.foundation_id,owner_user_id=principal.user_id,title=body.title.strip(),draft_body=content,draft_visibility=body.visibility,kind='pdf' if body.asset_id else 'lesson' if body.lesson_version_id else 'text',asset_id=body.asset_id,lesson_version_id=body.lesson_version_id)
    db.add(value)
    await db.flush()
    if body.asset_id:
        value.index_state='ingesting'
        enqueue_job(db,principal.foundation_id,'knowledge.ingest',{'source_id':str(value.id),'draft_version':value.draft_version,'asset_id':str(value.asset_id)})
    return source_view(principal,value)

async def save_source(db,principal,source_id,body):
    permission(principal,'knowledge.write')
    value=await source(db,principal,source_id,True)
    if not can_edit(principal,value):
        raise ApiError(403,'source_read_only','Редактировать источник может его автор или администратор базы')
    check_version(value.draft_version,body.expected_version)
    if body.asset_id and body.asset_id!=value.asset_id:
        from app.modules.assets.service import require_asset
        asset=await require_asset(db,principal,body.asset_id)
        if asset.content_type!='application/pdf':raise ApiError(422,'unsupported_source','Нужен PDF с текстом')
    content=await imported_lesson(db,principal,body.lesson_version_id) if body.lesson_version_id else body.body
    value.title,value.draft_body,value.draft_visibility=body.title.strip(),content,body.visibility
    value.reviewed_version=None
    value.draft_version+=1
    value.lesson_version_id=body.lesson_version_id
    if body.asset_id and body.asset_id!=value.asset_id:
        value.asset_id=body.asset_id
        value.kind='pdf'
        value.index_state='ingesting'
        enqueue_job(db,principal.foundation_id,'knowledge.ingest',{'source_id':str(value.id),'draft_version':value.draft_version,'asset_id':str(value.asset_id)})
    return source_view(principal,value)

async def review_source(db,principal,source_id,expected_version):
    permission(principal,'knowledge.publish')
    value=await source(db,principal,source_id,True)
    check_version(value.draft_version,expected_version)
    if len(value.draft_body.strip())<10 or value.index_state=='ingesting':
        raise ApiError(422,'source_incomplete','Добавьте текст источника или дождитесь импорта')
    value.reviewed_version=value.draft_version
    return source_view(principal,value)

async def publish_source(db,principal,source_id,expected_version):
    permission(principal,'knowledge.publish')
    value=await source(db,principal,source_id,True)
    check_version(value.draft_version,expected_version)
    if value.reviewed_version!=value.draft_version or not value.draft_body.strip():
        raise ApiError(409,'review_required','Сначала согласуйте эту редакцию источника')
    number=(await db.scalar(select(func.max(SourceVersion.number)).where(SourceVersion.source_id==value.id)) or 0)+1
    version=SourceVersion(source_id=value.id,foundation_id=principal.foundation_id,number=number,title=value.title,body=value.draft_body,visibility=value.draft_visibility)
    db.add(version)
    await db.flush()
    value.current_version_id=version.id
    value.archived=False
    value.index_state='queued'
    value.index_error=None
    value.index_generation+=1
    value.draft_version+=1
    value.reviewed_version=None
    enqueue_job(db,principal.foundation_id,'knowledge.index',{'source_id':str(value.id),'source_version_id':str(version.id),'generation':value.index_generation})
    return source_view(principal,value)

async def archive_source(db,principal,source_id,expected_version):
    permission(principal,'knowledge.publish')
    value=await source(db,principal,source_id,True)
    check_version(value.draft_version,expected_version)
    value.archived=True
    value.index_generation+=1
    value.index_state='withdrawn'
    value.draft_version+=1
    return source_view(principal,value)

async def reindex(db,principal,source_id,expected_version):
    permission(principal,'knowledge.publish')
    value=await source(db,principal,source_id,True)
    check_version(value.draft_version,expected_version)
    if value.archived or not value.current_version_id:
        raise ApiError(409,'source_unpublished','Источник не опубликован')
    value.index_generation+=1
    value.index_state='queued'
    value.index_error=None
    enqueue_job(db,principal.foundation_id,'knowledge.index',{'source_id':str(value.id),'source_version_id':str(value.current_version_id),'generation':value.index_generation})
    return source_view(principal,value)


def visible_query(principal):
    query=select(KnowledgeChunk,SourceVersion).join(SourceVersion,SourceVersion.id==KnowledgeChunk.source_version_id).join(KnowledgeSource,KnowledgeSource.current_version_id==SourceVersion.id).where(KnowledgeSource.foundation_id==principal.foundation_id,KnowledgeSource.archived.is_(False),KnowledgeSource.index_state=='ready')
    if not principal.has_permission('knowledge.read'):
        query=query.where(SourceVersion.visibility=='all')
    return query

def fragment_view(chunk,version):
    return dict(id=chunk.id,source_id=version.source_id,source_version_id=version.id,title=version.title,text=chunk.text)

async def search(db,principal,text,limit=8):
    import re
    terms=re.findall(r'[^\W_]+',text[:1000].casefold(),flags=re.UNICODE)[:24]
    if not terms:return []
    query_text=func.websearch_to_tsquery('russian',' OR '.join('\"'+term+'\"' for term in terms))
    query=visible_query(principal).where(KnowledgeChunk.search_document.op('@@')(query_text)).order_by(func.ts_rank_cd(KnowledgeChunk.search_document,query_text).desc(),KnowledgeChunk.id).limit(limit)
    return [fragment_view(chunk,version) for chunk,version in (await db.execute(query)).all()]

async def fragments_by_id(db,principal,ids):
    if not ids:return []
    parsed=[]
    for value in ids:
        try:parsed.append(UUID(str(value)))
        except ValueError:raise ApiError(422,'citation_invalid','Источник цитаты не найден')
    rows=(await db.execute(visible_query(principal).where(KnowledgeChunk.id.in_(parsed)))).all()
    by_id={str(chunk.id):fragment_view(chunk,version) for chunk,version in rows}
    return [by_id[str(value)] for value in parsed if str(value) in by_id]

async def notify_staff(db,foundation_id,question):
    from app.modules.messaging.consumers import enqueue_notice
    users=(await db.scalars(select(User).join(StaffMembership,StaffMembership.user_id==User.id).join(PermissionGrant,PermissionGrant.membership_id==StaffMembership.id).where(User.foundation_id==foundation_id,User.account_state=='active',StaffMembership.revoked_at.is_(None),PermissionGrant.revoked_at.is_(None),PermissionGrant.permission=='knowledge.write',PermissionGrant.scope_type=='foundation').distinct().limit(20))).all()
    for user in users:
        enqueue_notice(db,foundation_id,user.id,'Вопрос по материалам фонда',question.text+'\nОткрыть очередь: /fund/knowledge')

async def create_question(db,principal,text,kind='unknown'):
    item=KnowledgeQuestion(foundation_id=principal.foundation_id,user_id=principal.user_id,registration_id=None if principal.user_id else principal.registration_id,text=text,kind=kind)
    owner_scope(principal,KnowledgeQuestion)
    db.add(item)
    await db.flush()
    await notify_staff(db,principal.foundation_id,item)
    return item

async def ask_mentor(db,principal,text):
    fragments=await search(db,principal,text)
    item=MentorRun(foundation_id=principal.foundation_id,user_id=principal.user_id,registration_id=None if principal.user_id else principal.registration_id,question=text)
    owner_scope(principal,MentorRun)
    db.add(item)
    await db.flush()
    if not fragments:
        question=await create_question(db,principal,text)
        item.state,item.question_id='unknown',question.id
    else:
        run=await enqueue_ai_run(db,principal,'mentor',{'question':text,'fragments':[{**fragment,'id':str(fragment['id']),'source_id':str(fragment['source_id']),'source_version_id':str(fragment['source_version_id'])} for fragment in fragments]},source_refs=[str(fragment['id']) for fragment in fragments])
        item.ai_run_id,item.state=run.id,run.state
    return await mentor_view(db,principal,item.id)

async def owned_run(db,principal,run_id,lock=False):
    query=select(MentorRun).where(MentorRun.id==run_id,MentorRun.foundation_id==principal.foundation_id,owner_scope(principal,MentorRun))
    item=await db.scalar(query.with_for_update() if lock else query)
    if item is None:raise ApiError(404,'mentor_run_not_found','Вопрос не найден')
    return item

async def mentor_view(db,principal,run_id):
    item=await owned_run(db,principal,run_id)
    run=await db.get(AIRun,item.ai_run_id) if item.ai_run_id else None
    state=item.state
    answer=item.answer
    citations=await fragments_by_id(db,principal,item.citation_ids)
    if len(citations)!=len(item.citation_ids):state,answer='sources_unavailable',None
    if run and state in {'queued','calling'}:state=run.state
    if run and run.state=='succeeded' and item.state in {'queued','calling'}:
        output=run.output or {}
        citations=await fragments_by_id(db,principal,output.get('citation_ids',[]))
        allowed=set(run.source_refs)
        valid=bool(citations) and len(citations)==len(output.get('citation_ids',[])) and set(output.get('citation_ids',[])).issubset(allowed)
        if output.get('unknown') or not valid:
            state='unknown'
        else:state,answer='answered',output.get('answer')
    fragments=await search(db,principal,item.question)
    # Human answers remain available to the owner even with the provider disabled.
    if item.question_id:
        approved=await db.scalar(select(ApprovedAnswer).where(ApprovedAnswer.question_id==item.question_id,ApprovedAnswer.published_source_id.is_not(None)))
        if approved:
            published=await db.get(KnowledgeSource,approved.published_source_id)
            if published and not published.archived and published.index_state=='ready':
                version=await db.get(SourceVersion,published.current_version_id)
                state,answer='answered_by_coordinator',version.body
                rows=(await db.execute(visible_query(principal).where(SourceVersion.id==version.id))).all()
                citations=[fragment_view(chunk,source_version) for chunk,source_version in rows]
    return dict(id=item.id,question=item.question,state=state,answer=answer,fragments=fragments,citations=citations,question_id=item.question_id,error_code=run.error_code if run else None,model=run.model if run else None,prompt_version=run.prompt_version if run else None)

async def mentor_history(db,principal):
    ids=(await db.scalars(select(MentorRun.id).where(MentorRun.foundation_id==principal.foundation_id,owner_scope(principal,MentorRun)).order_by(MentorRun.created_at.desc()).limit(30))).all()
    return [await mentor_view(db,principal,item) for item in ids]

async def escalate(db,principal,run_id,kind='question'):
    item=await owned_run(db,principal,run_id,True)
    if item.question_id is None or kind=='report':
        question=await create_question(db,principal,item.question,kind)
        if item.question_id is None:item.question_id=question.id
        return {'question_id':str(question.id),'state':'queued_for_coordinator'}
    return {'question_id':str(item.question_id),'state':'queued_for_coordinator'}

async def claim_registration(db,registration_id,user_id):
    from app.core.models import RegistrationSession
    registration=await db.get(RegistrationSession,registration_id)
    user=await db.get(User,user_id)
    if registration is None or user is None or registration.foundation_id!=user.foundation_id:raise ApiError(409,'owner_conflict','Не удалось перенести историю вопросов')
    for model in [MentorRun,KnowledgeQuestion]:
        items=(await db.scalars(select(model).where(model.registration_id==registration_id,model.foundation_id==user.foundation_id).with_for_update())).all()
        for item in items:item.user_id,item.registration_id=user_id,None


async def question_list(db,principal):
    permission(principal,'knowledge.read')
    items=(await db.scalars(select(KnowledgeQuestion).where(KnowledgeQuestion.foundation_id==principal.foundation_id).order_by(KnowledgeQuestion.created_at.desc()).limit(200))).all()
    result=[]
    for item in items:
        answer=await db.scalar(select(ApprovedAnswer).where(ApprovedAnswer.question_id==item.id))
        result.append(dict(id=item.id,text=item.text,kind=item.kind,state=item.state,version=item.version,answer=(dict(id=str(answer.id),body=answer.body,version=answer.version,reviewed_version=answer.reviewed_version,published_source_id=str(answer.published_source_id) if answer.published_source_id else None,citation_ids=answer.citations) if answer else None)))
    return result

async def question(db,principal,question_id,lock=False):
    query=select(KnowledgeQuestion).where(KnowledgeQuestion.id==question_id,KnowledgeQuestion.foundation_id==principal.foundation_id)
    value=await db.scalar(query.with_for_update() if lock else query)
    if value is None:raise ApiError(404,'question_not_found','Вопрос не найден')
    return value

async def save_answer(db,principal,question_id,body):
    permission(principal,'knowledge.write')
    item=await question(db,principal,question_id,True)
    fragments=await fragments_by_id(db,principal,body.citation_ids)
    if len(fragments)!=len(body.citation_ids):raise ApiError(422,'citation_unavailable','Один из источников недоступен')
    # A coordinator answer is published to its asker; private staff-only fragments
    # cannot be turned into an all-volunteer source by selecting their IDs.
    if body.citation_ids:
        private=await db.scalar(select(KnowledgeChunk.id).join(SourceVersion).where(KnowledgeChunk.id.in_(body.citation_ids),SourceVersion.visibility!='all').limit(1))
        if private:raise ApiError(422,'private_citation','Для ответа волонтёру нужны общедоступные материалы фонда')
    answer=await db.scalar(select(ApprovedAnswer).where(ApprovedAnswer.question_id==item.id).with_for_update())
    check_version(answer.version if answer else 0,body.expected_version)
    if answer and answer.author_user_id!=principal.user_id and not principal.has_permission('knowledge.manage'):
        raise ApiError(403,'answer_read_only','Редактировать ответ может его автор')
    if answer is None:
        answer=ApprovedAnswer(foundation_id=principal.foundation_id,question_id=item.id,author_user_id=principal.user_id,body=body.body.strip(),citations=[str(value) for value in body.citation_ids])
        db.add(answer)
    else:
        answer.body,answer.citations=body.body.strip(),[str(value) for value in body.citation_ids]
        answer.version+=1
        answer.reviewed_version=None
        # The published source pointer remains independent of this mutable answer.
    await db.flush()
    return {'id':str(answer.id),'version':answer.version,'state':'draft'}

async def review_answer(db,principal,question_id,expected_version):
    permission(principal,'knowledge.publish')
    await question(db,principal,question_id,True)
    answer=await db.scalar(select(ApprovedAnswer).where(ApprovedAnswer.question_id==question_id).with_for_update())
    if answer is None:raise ApiError(404,'answer_not_found','Ответ не найден')
    check_version(answer.version,expected_version)
    if len(answer.body.strip())<10:raise ApiError(422,'answer_incomplete','Добавьте полный ответ')
    answer.reviewed_version=answer.version
    return {'id':str(answer.id),'version':answer.version,'state':'reviewed'}

async def publish_answer(db,principal,question_id,expected_version):
    from .schemas import SourceCreate
    from app.modules.messaging.consumers import enqueue_notice
    permission(principal,'knowledge.publish')
    item=await question(db,principal,question_id,True)
    answer=await db.scalar(select(ApprovedAnswer).where(ApprovedAnswer.question_id==item.id).with_for_update())
    if answer is None:raise ApiError(404,'answer_not_found','Ответ не найден')
    check_version(answer.version,expected_version)
    if answer.reviewed_version!=answer.version:raise ApiError(409,'review_required','Сначала согласуйте эту редакцию ответа')
    
    refs=await fragments_by_id(db,principal,answer.citations)
    if len(refs)!=len(answer.citations):raise ApiError(409,'citation_unavailable','Источник отозван. Проверьте ответ заново')
    if answer.published_source_id:
        existing=await source(db,principal,answer.published_source_id,True)
        current=await db.get(SourceVersion,existing.current_version_id)
        if current and current.body==answer.body and not existing.archived:
            return {'source_id':str(existing.id),'state':existing.index_state}
        existing.title,existing.draft_body,existing.draft_visibility=item.text[:300],answer.body,'all'
        existing.draft_version+=1
        existing.reviewed_version=None
        created=source_view(principal,existing)
    else:
        created=await create_source(db,principal,SourceCreate(title=item.text[:300],body=answer.body))
    await review_source(db,principal,created['id'],created['version'])
    published=await publish_source(db,principal,created['id'],created['version'])
    answer.published_source_id=published['id']
    item.state='answered'
    item.version+=1
    if item.user_id:
        enqueue_notice(db,principal.foundation_id,item.user_id,'Координатор ответил на вопрос',answer.body+'\nОткрыть наставника: /mentor')
    return {'source_id':str(answer.published_source_id),'state':'queued_for_index'}

async def builder_draft(db,principal,body):
    permission(principal,'learning.write')
    fragments=await fragments_by_id(db,principal,body.source_chunk_ids)
    if len(fragments)!=len(body.source_chunk_ids):raise ApiError(422,'source_unavailable','Выберите опубликованные материалы')
    private=await db.scalar(select(KnowledgeChunk.id).join(SourceVersion).where(KnowledgeChunk.id.in_(body.source_chunk_ids),SourceVersion.visibility!='all').limit(1))
    if private:raise ApiError(422,'private_source','Для урока волонтёров нужны общедоступные материалы фонда')
    run=await enqueue_ai_run(db,principal,'builder.draft',{'request':body.request,'fragments':[dict(id=str(part['id']),title=part['title'],text=part['text']) for part in fragments]},source_refs=[str(part['id']) for part in fragments],max_output_tokens=2000)
    return {'id':str(run.id),'state':run.state,'error_code':run.error_code}

async def apply_builder_draft(db,principal,lesson_id,body):
    from app.modules.learning import authoring
    from app.modules.learning.models import LessonDraft
    from app.modules.learning.schemas import DraftSave
    permission(principal,'learning.write')
    permission(principal,'learning.read')
    run=await db.scalar(select(AIRun).where(AIRun.id==body.run_id,AIRun.foundation_id==principal.foundation_id,AIRun.actor_id==principal.actor_id,AIRun.task=='builder.draft'))
    if run is None:raise ApiError(404,'ai_run_not_found','Черновик не найден')
    if run.state!='succeeded':raise ApiError(409,'ai_not_ready','Черновик ещё не готов')
    citations=await fragments_by_id(db,principal,run.output.get('citation_ids',[]))
    if not citations or len(citations)!=len(run.output.get('citation_ids',[])) or not set(run.output.get('citation_ids',[])).issubset(set(run.source_refs)):
        raise ApiError(409,'source_unavailable','Источник черновика недоступен. Проверьте материалы')
    await authoring.lesson(db,principal,lesson_id,lock=True)
    draft=await db.scalar(select(LessonDraft).where(LessonDraft.lesson_id==lesson_id).with_for_update())
    if draft is None:raise ApiError(409,'draft_missing','Сначала откройте редактирование урока')
    if any(block.get('_ai_run_id')==str(run.id) for block in draft.blocks):return await authoring.author_lesson(db,principal,lesson_id)
    check_version(draft.version,body.expected_version)
    block={'type':'text','title':run.output['title'],'text':run.output['text'],'_ai_run_id':str(run.id),'_source_chunk_ids':run.source_refs}
    return await authoring.save_draft(db,principal,lesson_id,DraftSave(expected_version=draft.version,title=draft.title,minutes=draft.minutes,source=draft.source,blocks=[*draft.blocks,block]))
