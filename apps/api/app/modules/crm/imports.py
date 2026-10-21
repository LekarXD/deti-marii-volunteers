"""Bounded staged CSV/XLSX import. Contacts are records, never login identities."""
import csv
import hashlib
import io
import re
import zipfile
from collections import Counter
from datetime import date, datetime
from uuid import UUID
from sqlalchemy import select, or_, text, func
from app.core.errors import ApiError
from app.core.contact_policy import contact_guard
from .models import CrmVolunteer,ImportBatch,ImportRow,ImportExternalReference,ImportEffect,MergeReview,ContactEvent,utcnow
from .schemas import ImportBatchView,ImportBatchSummary,ImportRowView
from .service import check_version,nonempty,scoped_volunteer

MAX_BYTES=5*1024*1024
MAX_ROWS=2000
MAX_COLUMNS=50
FIELDS={'name','email','phone','telegram','external_id','context','no_contact'}


def cell_text(value):
    if value is None:return ''
    if isinstance(value,(date,datetime)):return value.isoformat()
    result=str(value).strip()
    if len(result)>4000:raise ApiError(422,'import_cell_too_large','В ячейке больше 4000 символов')
    return result


def parse_upload(blob,filename):
    if not blob or len(blob)>MAX_BYTES:raise ApiError(413,'import_too_large','Размер файла должен быть от 1 байта до 5 МБ')
    lower=filename.lower()
    if lower.endswith('.csv'):
        try:
            source=blob.decode('utf-8-sig')
            if '\x00' in source:raise ValueError()
            dialect=csv.Sniffer().sniff(source[:8192],delimiters=',;\t')
            rows=csv.reader(io.StringIO(source),dialect)
            matrix=[]
            for row in rows:
                if len(matrix)>MAX_ROWS:raise ApiError(422,'import_row_limit','В одном импорте можно обработать до 2000 строк')
                if len(row)>MAX_COLUMNS:raise ApiError(422,'import_column_limit','В файле больше 50 столбцов')
                matrix.append([cell_text(value) for value in row])
        except (UnicodeDecodeError,csv.Error,ValueError):raise ApiError(422,'invalid_csv','Загрузите CSV в кодировке UTF-8 с заголовками')
    elif lower.endswith('.xlsx'):
        try:
            with zipfile.ZipFile(io.BytesIO(blob)) as archive:
                entries=archive.infolist()
                if len(entries)>300 or sum(item.file_size for item in entries)>50*1024*1024 or any(item.file_size>20*1024*1024 for item in entries):
                    raise ApiError(422,'xlsx_expansion_limit','Распакованный XLSX слишком большой')
                if any(item.file_size>1024*1024 and item.file_size/max(item.compress_size,1)>200 for item in entries):
                    raise ApiError(422,'xlsx_expansion_limit','XLSX имеет слишком высокий коэффициент сжатия')
            try:from openpyxl import load_workbook
            except ImportError:raise ApiError(503,'xlsx_unavailable','Обработка XLSX пока недоступна. Используйте CSV',retryable=True)
            workbook=load_workbook(io.BytesIO(blob),read_only=True,data_only=False,keep_links=False)
            sheet=workbook.worksheets[0]
            if sheet.max_row and sheet.max_row>MAX_ROWS+1:raise ApiError(422,'import_row_limit','В одном импорте можно обработать до 2000 строк')
            if sheet.max_column and sheet.max_column>MAX_COLUMNS:raise ApiError(422,'import_column_limit','В файле больше 50 столбцов')
            matrix=[]
            for row in sheet.iter_rows(max_row=MAX_ROWS+2,max_col=min(sheet.max_column or MAX_COLUMNS,MAX_COLUMNS+1)):
                values=[cell_text(cell.value) for cell in row]
                if any(cell.data_type=='f' for cell in row):raise ApiError(422,'xlsx_formulas_not_supported','Сохраните значения вместо формул перед импортом')
                matrix.append(values)
                if len(matrix)>MAX_ROWS+1 and any(values):raise ApiError(422,'import_row_limit','В одном импорте можно обработать до 2000 строк')
            workbook.close()
        except ApiError:raise
        except Exception:raise ApiError(422,'invalid_xlsx','Не удалось прочитать XLSX. Проверьте файл')
    else:raise ApiError(422,'unsupported_import_type','Поддерживаются CSV и XLSX')
    while matrix and not any(matrix[-1]):matrix.pop()
    if len(matrix)<2:raise ApiError(422,'empty_import','Добавьте заголовки и хотя бы одну строку')
    columns=matrix[0]
    while columns and not columns[-1]:columns.pop()
    if not columns or any(not value for value in columns) or len(set(columns))!=len(columns):raise ApiError(422,'invalid_headers','Названия столбцов должны быть непустыми и уникальными')
    raw=[]
    for number,row in enumerate(matrix[1:],2):
        if not any(row):continue
        if len(row)>len(columns) and any(row[len(columns):]):raise ApiError(422,'row_column_mismatch',f'В строке {number} больше значений, чем заголовков')
        raw.append((number,{column:row[index] if index<len(row) else '' for index,column in enumerate(columns)}))
    return columns,raw


async def batch_view(db,batch):
    rows=(await db.scalars(select(ImportRow).where(ImportRow.batch_id==batch.id).order_by(ImportRow.line_number))).all()
    return ImportBatchView(id=batch.id,checksum=batch.checksum,filename=batch.filename,columns=batch.columns,mapping=batch.mapping,source_system=batch.source_system,
        state=batch.state,version=batch.version,created_at=batch.created_at,applied_at=batch.applied_at,
        rows=[ImportRowView(id=row.id,line_number=row.line_number,raw=row.raw,normalized=row.normalized,decision=row.decision,volunteer_id=row.volunteer_id,errors=row.errors,resolution_reason=row.resolution_reason) for row in rows],
        counts=dict(Counter(row.decision for row in rows)))


async def batch_summary(db,batch):
    counts=dict((await db.execute(select(ImportRow.decision,func.count()).where(ImportRow.batch_id==batch.id).group_by(ImportRow.decision))).all())
    return ImportBatchSummary(id=batch.id,checksum=batch.checksum,filename=batch.filename,columns=batch.columns,mapping=batch.mapping,source_system=batch.source_system,
        state=batch.state,version=batch.version,created_at=batch.created_at,applied_at=batch.applied_at,counts=counts)


async def scoped_batch(db,principal,batch_id,lock=False):
    query=select(ImportBatch).where(ImportBatch.foundation_id==principal.foundation_id,ImportBatch.id==batch_id)
    if lock:query=query.with_for_update()
    batch=await db.scalar(query)
    if not batch:raise ApiError(404,'import_not_found','Импорт не найден')
    return batch


async def upload(db,principal,blob,filename):
    checksum=hashlib.sha256(blob).hexdigest()
    await db.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:key,0))'),{'key':f'import:{principal.foundation_id}:{checksum}'})
    existing=await db.scalar(select(ImportBatch).where(ImportBatch.foundation_id==principal.foundation_id,ImportBatch.checksum==checksum))
    if existing:return await batch_view(db,existing)
    columns,raw=parse_upload(blob,filename)
    batch=ImportBatch(foundation_id=principal.foundation_id,checksum=checksum,filename=filename[:240],columns=columns,author_id=principal.actor_id)
    db.add(batch);await db.flush()
    for line,values in raw:db.add(ImportRow(batch_id=batch.id,line_number=line,raw=values))
    await db.flush();return await batch_view(db,batch)


async def map_batch(db,principal,batch_id,command):
    batch=await scoped_batch(db,principal,batch_id,lock=True);check_version(batch.version,command.expected_version)
    if batch.state=='applied':raise ApiError(409,'import_already_applied','Применённый импорт нельзя менять')
    if not command.mapping.get('name') or set(command.mapping)-FIELDS or any(column not in batch.columns for column in command.mapping.values()):
        raise ApiError(422,'invalid_mapping','Укажите столбец с именем и существующие столбцы для остальных полей')
    batch.mapping=command.mapping;batch.source_system=nonempty(command.source_system);batch.state='mapped';batch.version+=1
    for row in (await db.scalars(select(ImportRow).where(ImportRow.batch_id==batch.id))).all():
        row.normalized={};row.decision='unmapped';row.errors=[];row.volunteer_id=None;row.resolution_reason=''
    await db.flush();return await batch_view(db,batch)


def normalize(raw,mapping):
    value={key:cell_text(raw.get(column,'')) for key,column in mapping.items()}
    errors=[]
    if not value.get('name'):errors.append('Нет имени')
    if len(value.get('name',''))>240:errors.append('Имя длиннее 240 символов')
    if any(text.startswith('=') for text in value.values()):errors.append('Формулы не поддерживаются: сохраните значения')
    email=value.get('email','').lower()
    if email and not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email):errors.append('Некорректная почта')
    phone=re.sub(r'\D','',value.get('phone',''))
    if phone:
        if len(phone)==11 and phone[0]=='8':phone='7'+phone[1:]
        if not 10<=len(phone)<=15:errors.append('Некорректный телефон')
        phone='+'+phone
    telegram=value.get('telegram','').strip().lstrip('@').lower()
    if telegram and not re.fullmatch(r'[A-Za-z0-9_]{5,32}',telegram):errors.append('Некорректный Telegram')
    if not (email or phone or telegram):errors.append('Нет контакта для проверки')
    preference=value.get('no_contact','').strip().lower()
    if preference not in ('','0','1','true','false','да','нет','yes','no'):errors.append('Не удалось распознать просьбу не связываться')
    value.update(email=email,phone=phone,telegram='@'+telegram if telegram else '',no_contact=preference in ('1','true','да','yes'))
    if len(value.get('external_id',''))>240:errors.append('Внешний ID длиннее 240 символов')
    return value,errors


async def dry_run(db,principal,batch_id,command):
    batch=await scoped_batch(db,principal,batch_id,lock=True);check_version(batch.version,command.expected_version)
    if batch.state not in ('mapped','previewed'):raise ApiError(409,'mapping_required','Сначала сопоставьте столбцы')
    rows=(await db.scalars(select(ImportRow).where(ImportRow.batch_id==batch.id).order_by(ImportRow.line_number))).all()
    seen={}
    for row in rows:
        normalized,errors=normalize(row.raw,batch.mapping);row.normalized=normalized;row.errors=errors;row.volunteer_id=None;row.resolution_reason=''
        row.decision='error' if errors else 'create'
        if errors:continue
        external_id=normalized.get('external_id')
        if external_id:
            reference=await db.scalar(select(ImportExternalReference).where(ImportExternalReference.foundation_id==principal.foundation_id,
                ImportExternalReference.source_system==batch.source_system,ImportExternalReference.external_id==external_id))
            if reference:
                target=await scoped_volunteer(db,principal.foundation_id,reference.volunteer_id,allow_alias=True)
                row.volunteer_id=target.merged_into_id or target.id;row.decision='link'
        if row.decision=='create':
            conditions=[(func.lower(CrmVolunteer.contacts[key].astext) if key in ('email','telegram') else CrmVolunteer.contacts[key].astext)==normalized[key] for key in ('email','phone','telegram') if normalized.get(key)]
            matches=(await db.scalars(select(CrmVolunteer).where(CrmVolunteer.foundation_id==principal.foundation_id,CrmVolunteer.merged_into_id.is_(None),or_(*conditions)).limit(3))).all()
            if matches:
                row.decision='review';row.volunteer_id=matches[0].id if len(matches)==1 else None
                row.errors=['Похожий контакт уже есть. Нужно решение координатора']
                db.add(MergeReview(foundation_id=principal.foundation_id,import_row_id=row.id,target_volunteer_id=row.volunteer_id,state='pending',reason='Совпадение контактных данных',author_id=principal.actor_id))
        signatures=[('external_id',external_id)] if external_id else [(key,normalized[key]) for key in ('email','phone','telegram') if normalized.get(key)]
        for signature in signatures:
            if signature in seen:
                previous=seen[signature]
                for duplicate in (row,previous):duplicate.decision='review';duplicate.errors=list(dict.fromkeys([*duplicate.errors,'Повтор контакта или внешнего ID внутри файла']))
            else:seen[signature]=row
    batch.state='previewed';batch.version+=1
    await db.flush();return await batch_view(db,batch)


async def resolve_row(db,principal,batch_id,row_id,command):
    batch=await scoped_batch(db,principal,batch_id,lock=True);check_version(batch.version,command.expected_version)
    if batch.state!='previewed':raise ApiError(409,'preview_required','Сначала выполните проверку импорта')
    row=await db.scalar(select(ImportRow).where(ImportRow.batch_id==batch.id,ImportRow.id==row_id).with_for_update())
    if not row:raise ApiError(404,'import_row_not_found','Строка не найдена')
    if row.decision=='error' and command.decision!='skip':raise ApiError(422,'invalid_import_row','Исправьте исходный файл или пропустите ошибочную строку')
    if command.decision=='link':
        if not command.volunteer_id:raise ApiError(422,'merge_target_required','Выберите карточку контакта')
        target=await scoped_volunteer(db,principal.foundation_id,command.volunteer_id)
        row.volunteer_id=target.id
    else:row.volunteer_id=None
    row.decision=command.decision;row.resolution_reason=nonempty(command.reason);row.errors=[]
    reviews=(await db.scalars(select(MergeReview).where(MergeReview.import_row_id==row.id,MergeReview.state=='pending'))).all()
    for review in reviews:review.state='resolved';review.target_volunteer_id=row.volunteer_id
    batch.version+=1;await db.flush();return await batch_view(db,batch)


async def apply_batch(db,principal,batch_id,command):
    await contact_guard(db,principal.foundation_id)
    batch=await scoped_batch(db,principal,batch_id,lock=True)
    # A second apply cannot create effects, even when a client lost the first result.
    if batch.state=='applied':return await batch_view(db,batch)
    check_version(batch.version,command.expected_version)
    if batch.state!='previewed':raise ApiError(409,'preview_required','Сначала проверьте импорт')
    rows=(await db.scalars(select(ImportRow).where(ImportRow.batch_id==batch.id).order_by(ImportRow.line_number).with_for_update())).all()
    if any(row.decision in ('review','error','unmapped') for row in rows):raise ApiError(422,'import_unresolved','Решите спорные строки или пропустите их перед применением')
    await db.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:key,0))'),{'key':f'import-source:{principal.foundation_id}:{batch.source_system}'})
    for row in rows:
        if row.decision=='skip':continue
        existing=await db.scalar(select(ImportEffect).where(ImportEffect.row_id==row.id))
        if existing:continue
        normalized=row.normalized;external_id=normalized.get('external_id')
        reference=await db.scalar(select(ImportExternalReference).where(ImportExternalReference.foundation_id==principal.foundation_id,
            ImportExternalReference.source_system==batch.source_system,ImportExternalReference.external_id==external_id)) if external_id else None
        if reference and row.decision=='create':raise ApiError(409,'import_preview_stale','Внешний ID уже импортирован. Повторите проверку')
        if row.decision=='link':
            target=await scoped_volunteer(db,principal.foundation_id,row.volunteer_id,lock=True)
            if reference and reference.volunteer_id not in (target.id,*list((await db.scalars(select(CrmVolunteer.id).where(CrmVolunteer.merged_into_id==target.id,CrmVolunteer.foundation_id==principal.foundation_id))).all())):
                raise ApiError(409,'external_identity_conflict','Внешний ID связан с другой карточкой. Сначала разрешите дубль')
        else:
            # Recheck contact collisions under source lock, including other batches applied after preview.
            conditions=[(func.lower(CrmVolunteer.contacts[key].astext) if key in ('email','telegram') else CrmVolunteer.contacts[key].astext)==normalized[key] for key in ('email','phone','telegram') if normalized.get(key)]
            collision=await db.scalar(select(CrmVolunteer.id).where(CrmVolunteer.foundation_id==principal.foundation_id,CrmVolunteer.merged_into_id.is_(None),or_(*conditions)).limit(1))
            if collision and not row.resolution_reason:raise ApiError(409,'import_preview_stale','Появился похожий контакт. Повторите проверку и решите дубль')
            target=CrmVolunteer(foundation_id=principal.foundation_id,display_name=normalized['name'],contacts={key:normalized[key] for key in ('email','phone','telegram') if normalized.get(key)},
                context=normalized.get('context',''),relationship_state='unverified',no_contact=normalized.get('no_contact',False))
            db.add(target);await db.flush();row.volunteer_id=target.id
        if normalized.get('no_contact'):target.no_contact=True
        if row.decision=='link':target.version+=1;target.updated_at=utcnow()
        if external_id and reference is None:db.add(ImportExternalReference(foundation_id=principal.foundation_id,source_system=batch.source_system,external_id=external_id,volunteer_id=target.id))
        if target.no_contact:
            from .service import cancel_open_tasks
            await cancel_open_tasks(db,target,principal,'Просьба не связываться сохранена при импорте')
        db.add(ImportEffect(row_id=row.id,volunteer_id=target.id,effect=row.decision,snapshot=normalized,author_id=principal.actor_id))
        db.add(ContactEvent(volunteer_id=target.id,kind='historical_import',direction='recorded',text=f'Импорт {batch.source_system}: строка {row.line_number}. Актуальность данных требует проверки.',author_id=principal.actor_id))
        await db.flush()
    batch.state='applied';batch.applied_at=utcnow();batch.version+=1
    await db.flush();return await batch_view(db,batch)
