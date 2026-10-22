import {useEffect, useRef, useState, type DragEvent, type FormEvent} from 'react';
import {Link, useParams} from 'react-router-dom';
import {useQuery, useQueryClient} from '@tanstack/react-query';
import {keys} from '../../api/keys';
import {Button, ErrorState, Field, Icon, Input, LoadingState, Segmented, Textarea, cx} from '../../ui';
import {command, photoProblem, photoTypes, readGroup, readGroups, readParticipant, uploadPhoto, type Group, type Participant, type ParticipantInput, type Ward, type WardGroup} from './api';
import {MEMO_TAGS_MAX, MEMO_TAG_LENGTH, MemoIcon, MemoTags, WardPhoto, ageLabel, memoBlocks, thisYear, wardPhotoUrl} from './wards';
import './participants.css';

type Draft = Required<Omit<ParticipantInput,'birth_year'|'photo_asset_id'>> & {photo_asset_id:string|null};
type Block = typeof memoBlocks[number];
const today = () => new Intl.DateTimeFormat('sv-SE', {timeZone:'Europe/Moscow'}).format(new Date());
const nextDay = (day:string) => new Date(Date.parse(`${day}T00:00:00Z`) + 86400000).toISOString().slice(0, 10);
const clean = (value:string) => value.split(/\s+/).filter(Boolean).join(' ');
const message = (error:unknown) => error instanceof Error ? error.message : 'Не удалось сохранить. Попробуйте ещё раз.';
const toDraft = (ward?:Ward):Draft => ({display_name:ward?.display_name ?? '', about:ward?.about ?? '', communication:ward?.communication ?? '', support:ward?.support ?? '', interests:ward?.interests ?? '',
  communication_tags:ward?.communication_tags ?? [], support_tags:ward?.support_tags ?? [], interests_tags:ward?.interests_tags ?? [], photo_asset_id:ward?.photo_asset_id ?? null, lifecycle:ward?.lifecycle ?? 'active'});

/** `/fund/participants/new` and `/fund/participants/:id/edit`: the card form with a live volunteer preview. */
export function ParticipantFormPage() {
  const {id=''}=useParams();
  const ward=useQuery({queryKey:keys.detail('participants',id),queryFn:({signal})=>readParticipant(id,signal),enabled:!!id});
  const groups=useQuery({queryKey:keys.list('participant-groups',{archived:false}),queryFn:({signal})=>readGroups(signal)});
  const back=id?{to:`/fund/participants/${id}`,label:ward.data?.display_name??'Карточка'}:{to:'/fund/participants',label:'Подопечные'};
  return <>
    <Link className="ward-back" to={back.to}><Icon name="chevron-left"/>{back.label}</Link>
    <div className="page-head"><h1 className="h1">{id?'Изменить карточку':'Новый подопечный'}</h1></div>
    {id && ward.isPending ? <LoadingState/> : id && ward.error ? <ErrorState error={ward.error} retry={()=>void ward.refetch()}/> : <WardForm key={ward.data?.id??'new'} ward={ward.data} groups={groups.data?.items??[]}/>}
  </>;
}

function WardForm({ward, groups}:{ward?:Ward;groups:Group[]}) {
  const client=useQueryClient();
  const [draft,setDraft]=useState(()=>toDraft(ward)),[year,setYear]=useState(ward?.birth_year?String(ward.birth_year):'');
  const [saved,setSaved]=useState<{id:string;version:number}|null>(ward?{id:ward.id,version:ward.version}:null);
  const [membership,setMembership]=useState<WardGroup|null>(ward?.groups[0]??null),[group,setGroup]=useState(ward?.groups[0]?.id??'');
  const [extra,setExtra]=useState(()=>Object.fromEntries(memoBlocks.map(b=>[b.tags,(ward?.[b.tags]??[]).filter(tag=>!b.presets.includes(tag))])) as Record<Block['tags'],string[]>);
  const [own,setOwn]=useState<Record<string,string>>({}),[notes,setNotes]=useState(()=>new Set(memoBlocks.filter(b=>ward?.[b.note]).map(b=>b.note)));
  const [photo,setPhoto]=useState<{url:string;name:string}|null>(null),[uploading,setUploading]=useState(false),[photoError,setPhotoError]=useState(''),[over,setOver]=useState(false);
  const [busy,setBusy]=useState(false),[error,setError]=useState(''),[done,setDone]=useState(false);
  const fileInput=useRef<HTMLInputElement>(null),pick=useRef(0);
  useEffect(()=>()=>{if(photo)URL.revokeObjectURL(photo.url);},[photo]);
  const change=(patch:Partial<Draft>)=>{setDraft(current=>({...current,...patch}));setDone(false);};
  const setField=<K extends keyof Draft>(key:K,value:Draft[K])=>change({[key]:value} as Partial<Draft>);
  const yearNumber=/^\d{4}$/.test(year)?Number(year):null,age=ageLabel(yearNumber);
  const groupTitle=groups.find(g=>g.id===group)?.title??(membership?.id===group?membership.title:'');
  const photoUrl=photo?.url??(ward&&draft.photo_asset_id&&draft.photo_asset_id===ward.photo_asset_id?wardPhotoUrl(ward):'');
  const name=clean(draft.display_name);
  const previewPerson:Pick<Participant,'id'|'display_name'|'photo_asset_id'>={id:ward?.id??'new',display_name:name||'?',photo_asset_id:null};

  async function choose(file?:File) {
    if(!file||busy)return;
    const problem=photoProblem(file);
    if(problem){setPhotoError(problem);return;}
    const token=++pick.current;
    setPhotoError('');setDone(false);setPhoto({url:URL.createObjectURL(file),name:file.name});setUploading(true);
    try{const asset=await uploadPhoto(file);if(token===pick.current)change({photo_asset_id:asset});}
    catch(e){if(token===pick.current){setPhoto(null);setPhotoError(message(e));}}
    finally{if(token===pick.current)setUploading(false);}
  }
  function removePhoto(){pick.current++;setPhoto(null);setUploading(false);setPhotoError('');change({photo_asset_id:null});}
  function drop(e:DragEvent){e.preventDefault();setOver(false);void choose(e.dataTransfer.files[0]);}
  function toggle(block:Block,tag:string){const tags=draft[block.tags];setField(block.tags,tags.includes(tag)?tags.filter(t=>t!==tag):[...tags,tag]);}
  function addOwn(block:Block){
    const tag=clean(own[block.tags]??'').slice(0,MEMO_TAG_LENGTH);
    if(!tag)return;
    if(![...block.presets,...extra[block.tags]].includes(tag))setExtra(current=>({...current,[block.tags]:[...current[block.tags],tag]}));
    if(!draft[block.tags].includes(tag)&&draft[block.tags].length<MEMO_TAGS_MAX)setField(block.tags,[...draft[block.tags],tag]);
    setOwn(current=>({...current,[block.tags]:''}));
  }
  /** Moving to another group ends today's membership and opens a new one; history stays in the group. */
  async function moveGroup(wardId:string) {
    if(group===(membership?.id??''))return;
    const day=today();
    if(membership){
      const current=await readGroup(membership.id,day);
      const until=membership.valid_from>=day?nextDay(membership.valid_from):day;
      await command(`/coord/groups/${membership.id}/memberships/${membership.membership_id}`,{valid_until:until,expected_version:current.version},'PATCH');
      setMembership(null);
    }
    if(group){
      const target=await readGroup(group,day);
      const added=await command<{id:string;valid_from:string}>(`/coord/groups/${group}/memberships`,{participant_id:wardId,valid_from:day,expected_version:target.version});
      setMembership({id:group,title:target.title,membership_id:added.id,valid_from:added.valid_from});
    }
  }
  async function save(e:FormEvent) {
    e.preventDefault();
    if(!name){setError('Укажите имя и фамилию.');return;}
    if(year&&(!yearNumber||yearNumber<1900||yearNumber>thisYear())){setError('Проверьте год рождения.');return;}
    setBusy(true);setError('');
    let stored=saved;
    try{
      const body={...draft,display_name:name,about:draft.about.trim(),birth_year:yearNumber};
      const result=stored?await command<Participant>(`/coord/participants/${stored.id}`,{...body,expected_version:stored.version},'PATCH'):await command<Participant>('/coord/participants',body);
      stored={id:result.id,version:result.version};setSaved(stored);
      await moveGroup(result.id);
      setDone(true);
    }catch(e){setError(stored&&stored!==saved?`Карточка сохранена, но группу изменить не удалось. ${message(e)}`:message(e));}
    finally{
      setBusy(false);
      await Promise.all(['participants','participant-groups','participant-group'].map(domain=>client.invalidateQueries({queryKey:keys.all(domain)})));
    }
  }

  return <form className="ward-split" onSubmit={save} noValidate>
    <div className="ward-main">
      <section className="ward-form-card" aria-labelledby="ward-form-who">
        <h2 className="h2" id="ward-form-who">Знакомство</h2>
        <div className="ward-who">
          <div className="ward-photo-col">
            <div className={cx('ward-photo-drop',photoUrl&&'has-photo',over&&'is-over')} onDragOver={e=>{e.preventDefault();setOver(true);}} onDragLeave={()=>setOver(false)} onDrop={drop}>
              <input ref={fileInput} type="file" accept={photoTypes.join(',')} className="sr-only" tabIndex={-1} aria-label="Фото подопечного" onChange={e=>{void choose(e.target.files?.[0]);e.target.value='';}}/>
              {photoUrl ? <>
                <img className="ward-photo-frame" src={photoUrl} alt="Фото подопечного"/>
                {photo&&<span className="ward-photo-name">{photo.name}</span>}
                {uploading&&<span className="meta" role="status">Загружаем фото…</span>}
                <div className="row ward-photo-actions"><Button variant="ghost" size="sm" disabled={busy} onClick={()=>fileInput.current?.click()}>Заменить</Button><Button variant="ghost" size="sm" disabled={busy} onClick={removePhoto}>Убрать</Button></div>
              </> : <>
                <span className="ward-photo-frame" aria-hidden="true"><Icon name="image"/></span>
                <Button variant="secondary" disabled={busy} onClick={()=>fileInput.current?.click()}><Icon name="upload"/>Загрузить фото</Button>
                <span className="meta">JPG, PNG или WebP до 5 МБ</span>
              </>}
              {photoError&&<p className="err" role="alert">{photoError}</p>}
            </div>
          </div>
          <div className="ward-who-fields">
            <Field label="Имя и фамилия"><Input type="text" required maxLength={200} value={draft.display_name} onChange={e=>change({display_name:e.target.value})} placeholder="Например, Миша Котов"/></Field>
            <div className="field"><label className="label" htmlFor="ward-year">Год рождения</label>
              <div className="ward-age-field"><input id="ward-year" className="input" type="text" inputMode="numeric" maxLength={4} placeholder="2014" value={year} onChange={e=>{setYear(e.target.value.replace(/\D/g,'').slice(0,4));setDone(false);}}/>{age&&<span className="ward-age-pill">{age}</span>}</div>
            </div>
            {(groups.length>0||membership)&&<div className="field"><span className="label" id="ward-group">Группа</span>
              <div className="ward-pick" role="radiogroup" aria-labelledby="ward-group">{[...groups.map(g=>({id:g.id,title:g.title})),...(membership&&!groups.some(g=>g.id===membership.id)?[membership]:[])].map(g=><button key={g.id} type="button" role="radio" aria-checked={group===g.id} className={group===g.id?'is-on':''} onClick={()=>{setGroup(g.id);setDone(false);}}>{g.title}</button>)}</div>
            </div>}
            <Field label="О человеке"><Textarea className="ward-about" maxLength={10000} placeholder="Пара фраз: чем живёт, что любит на занятиях" value={draft.about} onChange={e=>change({about:e.target.value})}/></Field>
            {ward&&<Segmented label="Карточка" value={draft.lifecycle} onChange={value=>change({lifecycle:value})} options={[{value:'active',label:'Активная'},{value:'archived',label:'В архиве'}]}/>}
          </div>
        </div>
      </section>

      <section className="ward-form-card" aria-labelledby="ward-form-memo">
        <h2 className="h2" id="ward-form-memo">Памятка для волонтёра</h2>
        {memoBlocks.map(block=>{const chosen=draft[block.tags],full=chosen.length>=MEMO_TAGS_MAX,inputId=`ward-own-${block.tags}`;return <div className="ward-form-block" key={block.tags}>
          <h3 className="h3"><MemoIcon icon={block.icon} art={block.art}/>{block.title}</h3>
          <div className="ward-pick">{[...block.presets,...extra[block.tags]].map(tag=>{const on=chosen.includes(tag);return <button key={tag} type="button" aria-pressed={on} className={on?'is-on':''} disabled={!on&&full} onClick={()=>toggle(block,tag)}>{on&&<Icon name="check"/>}{tag}</button>;})}</div>
          <div className="ward-pick-add"><label className="sr-only" htmlFor={inputId}>Своё: {block.title}</label><input id={inputId} className="input" type="text" placeholder="Своё" maxLength={MEMO_TAG_LENGTH} disabled={full} value={own[block.tags]??''} onChange={e=>setOwn(current=>({...current,[block.tags]:e.target.value}))} onKeyDown={e=>{if(e.key==='Enter'){e.preventDefault();addOwn(block);}}}/><Button variant="secondary" size="sm" disabled={full||!clean(own[block.tags]??'')} onClick={()=>addOwn(block)}>Добавить</Button></div>
          {notes.has(block.note) ? <Field label="Приписка" className="ward-note-field"><Textarea maxLength={10000} value={draft[block.note]} onChange={e=>setField(block.note,e.target.value)} placeholder="Коротко, если чипов не хватает"/></Field> : <Button variant="ghost" size="sm" className="ward-note-add" onClick={()=>setNotes(current=>new Set(current).add(block.note))}><Icon name="plus"/>Приписка</Button>}
        </div>;})}
      </section>

      <div className="actions ward-form-actions">{done&&saved ? <>
        <span className="ward-done" role="status"><Icon name="check"/>Карточка сохранена</span>
        <Link className="btn btn-primary btn-lg" to={`/fund/participants/${saved.id}`}>Открыть карточку</Link>
      </> : <>
        <Button type="submit" size="lg" loading={busy} disabled={uploading}>Сохранить карточку</Button>
        <Link className="btn btn-ghost btn-lg" to={ward?`/fund/participants/${ward.id}`:'/fund/participants'}>Отмена</Link>
      </>}{error&&<p className="err ward-form-error" role="alert">{error}</p>}</div>
    </div>

    <aside className="ward-panel" aria-labelledby="ward-preview-title">
      <p className="eyebrow">Так увидит волонтёр</p>
      <div className="ward-preview-top">
        <WardPhoto person={previewPerson} size="lg" src={photoUrl||undefined}/>
        <div className="grow"><h2 className="h3 ward-preview-name" id="ward-preview-title">{name||'Имя подопечного'}</h2>{(age||groupTitle)&&<p className="meta">{[age,groupTitle].filter(Boolean).join(', ')}</p>}</div>
      </div>
      {memoBlocks.map(block=><div className="ward-preview-sec" key={block.tags}><span className="label">{block.title}</span><MemoTags tags={draft[block.tags]}/>{draft[block.note].trim()&&<p className="ward-memo-note">{draft[block.note].trim()}</p>}</div>)}
    </aside>
  </form>;
}
