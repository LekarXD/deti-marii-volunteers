import {appPath} from '../../basePath';
import {useEffect,useId,useRef,useState} from 'react';
import {Link,useSearchParams} from 'react-router-dom';
import {ApiError,api,getPrincipalKey} from '../../api/transport';
import {Button,DatePicker,EmptyState,ErrorState,Field,Icon,Input,LoadingState,Textarea,useToast} from '../../ui';
import {Profile,ProfileTag,ProfileUpdate,Asset,useProfile,useProfileCommand,today,dayMonth,moscowDay} from './api';
import {SuggestionBox,AcceptedSuggestions} from './SuggestionsPanel';
import {CertificateForm} from './DocumentsPage';
import {ConsentPanel,OwnDataPanel} from './PrivacyPanels';
import {ContactChangePanel} from './ContactChangePanel';
import {ProfileAIRunPanel} from './ProfileAIRunPanel';
import {ProfileAvailability} from './ProfileAvailability';
import {ProfileNotifications} from './ProfileNotifications';
import {addDays,canonTags,sameLabel,useProfileCatalog,useVolunteerFacts} from './profileHooks';
import './profile-page.css';

const tabs=[['about','Обо мне'],['time','Когда свободна'],['pause','Пауза'],['notif','Уведомления'],['docs','Документы'],['privacy','Приватность']] as const;
type Tab=typeof tabs[number][0];
/** Old links keep working: «Навыки» moved into «Обо мне», «Время» became «Когда свободна». */
const legacyTabs:Record<string,Tab>={skills:'about',avail:'time'};
const pickTab=(value:string|null):Tab=>tabs.some(([id])=>id===value)?value as Tab:(value&&legacyTabs[value])||'about';
const pickKinds:ProfileTag['kind'][]=['skill','interest','age_interest'];
const aiFields=[['ai_about','О себе'],['ai_skills','Навыки'],['ai_interests','Интересы']] as const;
const same=(a:unknown,b:unknown)=>JSON.stringify(a??null)===JSON.stringify(b??null);
const placeTags=(tags:ProfileTag[]=[])=>tags.filter(tag=>tag.kind==='place_interest');
const otherTags=(tags:ProfileTag[]=[])=>tags.filter(tag=>tag.kind!=='place_interest');
const toDraft=(p:Profile):ProfileUpdate=>({expected_version:p.version,display_name:p.display_name,about:p.about,tags:canonTags(p.tags),lifecycle:p.lifecycle as 'active'|'paused',paused_until:p.paused_until,photo_asset_id:p.photo_asset_id,ai_about:p.ai_about,ai_skills:p.ai_skills,ai_interests:p.ai_interests});
const when=(value:string)=>new Date(value).toLocaleDateString('ru',{day:'numeric',month:'long',year:'numeric'}).replace(/\s?г\.$/,'');
const revisionLabels:Record<string,string>={manual:'изменено вручную',suggestion_accept:'принято предложение',suggestion_revert:'предложение отменено'};

export function ProfilePage(){
 const query=useProfile(),[reset,setReset]=useState(0);
 if(query.isPending)return <LoadingState label="Загружаем профиль…"/>;
 if(query.error)return query.error instanceof ApiError&&query.error.code==='verified_identity_required'?<EmptyState title="Подтверди почту" description="Профиль доступен после входа по подтверждённой почте." action={<Link className="btn btn-primary" to="/login?next=/profile">Войти</Link>}/>:<ErrorState error={query.error} retry={()=>void query.refetch()}/>;
 return <ProfileEditor key={query.data.user_id+':'+reset} profile={query.data} reload={()=>void query.refetch().then(()=>setReset(v=>v+1))}/>;
}

function ProfileEditor({profile,reload}:{profile:Profile;reload:()=>void}){
 const [search,setSearch]=useSearchParams(),tab=pickTab(search.get('tab')),setTab=(next:Tab)=>setSearch({tab:next});
 const [draft,setDraft]=useState(()=>toDraft(profile)),[saved,setSaved]=useState(()=>toDraft(profile)),[editing,setEditing]=useState(!profile.about);
 const [photoBusy,setPhotoBusy]=useState(false),[photoError,setPhotoError]=useState<unknown>(null),{toast}=useToast();
 const save=useProfileCommand<Profile>('/me/profile','PUT',profile.version),catalog=useProfileCatalog(),facts=useVolunteerFacts();
 const latestDraft=useRef(draft),latestSaved=useRef(saved);latestDraft.current=draft;latestSaved.current=saved;
 const change=<K extends keyof ProfileUpdate>(key:K,value:ProfileUpdate[K])=>setDraft(old=>({...old,[key]:value}));
 const setTags=(tags:ProfileTag[])=>change('tags',canonTags(tags));
 const [seenPlaces]=useState(()=>placeTags(saved.tags).map(tag=>tag.label));

 /** Saves one section on top of the last saved profile, so other sections' unsaved edits stay local. Resolves to whether the section is now clean, or null on failure. */
 async function persist(patch:Partial<ProfileUpdate>,message:string|null){
  const submitted={...latestSaved.current,...patch};
  try{
   const value=toDraft(await save.mutateAsync(submitted)),latest=latestDraft.current,merged:ProfileUpdate={...value};let clean=true;
   for(const key of Object.keys(value) as (keyof ProfileUpdate)[]){if(key==='expected_version'||same(latest[key],submitted[key]))continue;Object.assign(merged,{[key]:latest[key]});if(key in patch)clean=false;}
   setDraft(merged);setSaved(value);if(message)toast(clean?message:'Сохранено. Новые изменения ещё не сохранены.');return clean;
  }catch{return null;}
 }

 const photoRequest=useRef<AbortController|null>(null),fileInput=useRef<HTMLInputElement>(null);useEffect(()=>()=>photoRequest.current?.abort(),[]);
 async function uploadPhoto(file:File){
  photoRequest.current?.abort();const abort=new AbortController();photoRequest.current=abort;const principal=getPrincipalKey();
  const current=()=>{if(abort.signal.aborted||getPrincipalKey()!==principal)throw new ApiError(0,'principal_changed','Аккаунт или страница изменились. Выбери файл заново.');};
  setPhotoBusy(true);setPhotoError(null);
  try{if(file.size>5*1024*1024||!['image/png','image/jpeg','image/webp'].includes(file.type))throw Error('Подойдёт PNG, JPEG или WebP до 5 МБ');
   const data=await file.arrayBuffer();current();const digest=await crypto.subtle.digest('SHA-256',data);current();const checksum=Array.from(new Uint8Array(digest)).map(b=>b.toString(16).padStart(2,'0')).join('');
   const intent=await api<Asset>('/assets/upload-intents',{method:'POST',body:{content_type:file.type,expected_size:file.size,checksum},signal:abort.signal});
   for(let offset=0;offset<data.byteLength;offset+=1024*1024){current();await api(`/assets/${intent.id}/upload`,{method:'PATCH',body:data.slice(offset,offset+1024*1024),signal:abort.signal,headers:{'X-Upload-Offset':String(offset),'Content-Type':'application/octet-stream'}});}
   current();const ready=await api<Asset>(`/assets/${intent.id}/complete-upload`,{method:'POST',signal:abort.signal});current();if(ready.state!=='ready')throw Error('Изображение ещё не готово');
   change('photo_asset_id',ready.id);await persist({photo_asset_id:ready.id},'Фото обновлено');
  }catch(error){if(!abort.signal.aborted&&getPrincipalKey()===principal)setPhotoError(error);}finally{if(photoRequest.current===abort){photoRequest.current=null;setPhotoBusy(false);}}
 }

 const aboutDirty=!same(draft.display_name,saved.display_name)||!same(draft.about,saved.about);
 const skillsDirty=!same(otherTags(draft.tags),otherTags(saved.tags)),placesDirty=!same(placeTags(draft.tags),placeTags(saved.tags));
 const aiDirty=aiFields.some(([key])=>draft[key]!==saved[key]);
 const placeOptions=[...new Map([...seenPlaces,...catalog.places].map(label=>[label.toLocaleLowerCase('ru'),label])).values()];
 const selectedPlaces=placeOptions.filter(label=>placeTags(draft.tags).some(tag=>sameLabel(tag.label,label)));
 const togglePlace=(label:string)=>setTags(draft.tags?.some(tag=>tag.kind==='place_interest'&&sameLabel(tag.label,label))?(draft.tags??[]).filter(tag=>!(tag.kind==='place_interest'&&sameLabel(tag.label,label))):[...(draft.tags??[]),{kind:'place_interest',label,level:'learn'}]);
 const paused=saved.lifecycle==='paused',eyebrow=paused?'Участие на паузе':facts.since?`Волонтёр с ${dayMonth(moscowDay(facts.since))}`:'';
 const saveAbout=()=>void persist({display_name:draft.display_name,about:draft.about},'Профиль сохранён').then(clean=>{if(clean)setEditing(false);});

 return <div className="vol-profile">
  <section className="card-hero prof-hero" aria-labelledby="profile-title">
   <div className="prof-hero-row">
    <span className={'prof-av'+(saved.photo_asset_id?' has-photo':'')} aria-hidden="true">{saved.photo_asset_id?<img src={appPath(`/api/v1/assets/${saved.photo_asset_id}/content`)} alt=""/>:<svg viewBox="0 0 24 24"><circle cx="12" cy="9" r="4.2"/><path d="M3.5 24a8.5 8.5 0 0 1 17 0"/></svg>}</span>
    <div className="grow">
     {eyebrow&&<p className="eyebrow">{eyebrow}</p>}
     <h1 className="hero-title" id="profile-title">{saved.display_name}</h1>
     {facts.role&&<p className="hero-sub">{facts.role}</p>}
    </div>
    <input ref={fileInput} type="file" className="sr-only" tabIndex={-1} aria-label="Фото профиля" accept="image/png,image/jpeg,image/webp" disabled={photoBusy} onChange={e=>{const file=e.target.files?.[0];e.target.value='';if(file)void uploadPhoto(file);}}/>
    <Button variant="secondary" size="lg" loading={photoBusy} onClick={()=>fileInput.current?.click()}>Изменить фото</Button>
   </div>
   {photoBusy&&<p className="prof-hero-note" role="status">Проверяем фото…</p>}
   {!!photoError&&<p className="err prof-hero-note" role="alert">{photoError instanceof Error?photoError.message:'Не получилось загрузить фото'}</p>}
  </section>

  <div className="tabs prof-tabs" role="tablist" aria-label="Разделы профиля">{tabs.map(([id,label],index)=><button key={id} id={'profile-tab-'+id} type="button" role="tab" className={tab===id?'is-on':undefined} aria-selected={tab===id} aria-controls="profile-panel" tabIndex={tab===id?0:-1} onKeyDown={event=>{let next=index;if(event.key==='ArrowRight')next=(index+1)%tabs.length;else if(event.key==='ArrowLeft')next=(index+tabs.length-1)%tabs.length;else if(event.key==='Home')next=0;else if(event.key==='End')next=tabs.length-1;else return;event.preventDefault();setTab(tabs[next][0]);document.getElementById('profile-tab-'+tabs[next][0])?.focus();}} onClick={()=>setTab(id)}>{label}</button>)}</div>

  {save.error&&<div className="prof-alert" role="alert"><p className="p">{save.error instanceof ApiError&&save.error.status===409?'Профиль изменился в другом окне.':save.error.message}</p>{save.error instanceof ApiError&&save.error.status===409&&<Button variant="secondary" size="sm" onClick={reload}>Загрузить актуальный профиль</Button>}</div>}

  <div id="profile-panel" className="prof-panel" role="tabpanel" aria-labelledby={'profile-tab-'+tab}>
   {tab==='about'&&<div className="prof-stack">
    <div className="grid-2">
     <section className="card action-card">
      <div className="row prof-card-head"><h2 className="h3">О себе</h2>{!editing&&<Button variant="ghost" size="sm" onClick={()=>setEditing(true)}>Изменить</Button>}</div>
      {editing?<>
       <Field label="Имя и фамилия"><Input value={draft.display_name} onChange={e=>change('display_name',e.target.value)} maxLength={200}/></Field>
       <Field label="О себе"><Textarea value={draft.about} onChange={e=>change('about',e.target.value)} rows={6} maxLength={8000}/></Field>
       <div className="actions"><Button disabled={!aboutDirty||save.isPending||photoBusy||!draft.display_name.trim()} onClick={saveAbout}>Сохранить</Button><Button variant="ghost" disabled={save.isPending} onClick={()=>{setDraft(old=>({...old,display_name:saved.display_name,about:saved.about}));setEditing(false);}}>Отмена</Button></div>
      </>:<p className="p prof-about">{saved.about||'Расскажи о себе: что нравится делать и чем хочется помогать.'}</p>}
     </section>
     <SkillsCard tags={draft.tags??[]} onChange={setTags} programs={catalog.programs} audiences={catalog.audiences} dirty={skillsDirty} busy={save.isPending} primary={!editing} onSave={()=>void persist({tags:canonTags([...otherTags(draft.tags),...placeTags(saved.tags)])},'Сохранено')}/>
    </div>
    <SuggestionBox version={draft.expected_version} onChanged={reload}/>
    <ContactsCard contacts={profile.contacts}/>
   </div>}
   {tab==='time'&&<ProfileAvailability places={{options:placeOptions,selected:selectedPlaces,onToggle:togglePlace,dirty:placesDirty,busy:save.isPending,save:()=>persist({tags:canonTags([...otherTags(saved.tags),...placeTags(draft.tags)])},null).then(result=>result!==null)}}/>}
   {tab==='pause'&&<PauseCard draft={draft} saved={saved} change={change} busy={save.isPending} save={persist}/>}
   {tab==='notif'&&<ProfileNotifications email={profile.contacts.find(contact=>contact.type==='email')?.value??null}/>}
   {tab==='docs'&&<section className="card prof-docs"><div className="row prof-card-head"><h2 className="h3">Справка о часах</h2><Link className="quiet-link" to="/hours/documents">Все справки</Link></div><CertificateForm action="download"/></section>}
   {tab==='privacy'&&<div className="prof-stack">
    <section className="card">
     <h2 className="h3 prof-card-title">Что видит ИИ</h2>
     <p className="p">Из отмеченных полей ИИ может готовить предложения для профиля. Каждое изменение сначала придёт тебе на проверку.</p>
     <div className="prof-rows">{aiFields.map(([key,label])=><div className="set-row" key={key}><div className="grow"><b>{label}</b></div><button type="button" className={'toggle'+(draft[key]?' is-on':'')} aria-pressed={!!draft[key]} aria-label={label} onClick={()=>change(key,!draft[key])}/></div>)}</div>
     {aiDirty&&<div className="actions"><Button loading={save.isPending} onClick={()=>void persist({ai_about:draft.ai_about,ai_skills:draft.ai_skills,ai_interests:draft.ai_interests},'Сохранено')}>Сохранить</Button></div>}
    </section>
    <ProfileAIRunPanel version={draft.expected_version}/>
    <AcceptedSuggestions version={draft.expected_version} onChanged={reload}/>
    <ConsentPanel/>
    <OwnDataPanel/>
    {profile.revisions.length>0&&<section className="card"><h2 className="h3 prof-card-title">История профиля</h2><div className="prof-history">{profile.revisions.map(revision=><details key={revision.id} className="prof-details"><summary>{when(revision.created_at)}, {revisionLabels[revision.source]??revision.source}</summary><p className="p prof-about">{String(revision.snapshot.about||'')}</p></details>)}</div></section>}
   </div>}
  </div>
 </div>;
}

type PickOption={kind:ProfileTag['kind'];label:string};
/** «Что умею и люблю»: own skills and interests plus the programs and audiences of open directions, as toggles. */
function SkillsCard({tags,onChange,programs,audiences,dirty,busy,primary,onSave}:{tags:ProfileTag[];onChange:(tags:ProfileTag[])=>void;programs:string[];audiences:string[];dirty:boolean;busy:boolean;primary:boolean;onSave:()=>void}){
 const id=useId(),[text,setText]=useState(''),[adding,setAdding]=useState(false);
 const [seen,setSeen]=useState<PickOption[]>(()=>tags.filter(tag=>pickKinds.includes(tag.kind)).map(({kind,label})=>({kind,label})));
 const options=[...new Map([...seen,...tags.filter(tag=>pickKinds.includes(tag.kind)),...programs.map(label=>({kind:'interest' as const,label})),...audiences.map(label=>({kind:'age_interest' as const,label}))].map(({kind,label})=>[label.trim().toLocaleLowerCase('ru'),{kind,label}])).values()];
 const isOn=(option:PickOption)=>tags.some(tag=>tag.kind===option.kind&&sameLabel(tag.label,option.label));
 const remember=(option:PickOption)=>setSeen(old=>old.some(item=>sameLabel(item.label,option.label))?old:[...old,option]);
 const toggle=(option:PickOption)=>{remember(option);onChange(isOn(option)?tags.filter(tag=>!(tag.kind===option.kind&&sameLabel(tag.label,option.label))):[...tags,{...option,level:'learn'}]);};
 const add=()=>{const label=text.trim();if(!label)return;const known=options.find(option=>sameLabel(option.label,label)),option=known??{kind:'skill' as const,label};remember(option);if(!isOn(option))onChange([...tags,{...option,level:'learn'}]);setText('');setAdding(false);};
 const skills=tags.filter(tag=>tag.kind==='skill');
 return <section className="card action-card">
  <h2 className="h3">Что умею и люблю</h2>
  <div className="pick" role="group" aria-label="Что умею и люблю">
   {options.map(option=>{const on=isOn(option);return <button key={option.kind+option.label} type="button" className={on?'is-on':undefined} aria-pressed={on} onClick={()=>toggle(option)}>{option.label}</button>;})}
   {!adding&&<button type="button" className="prof-pick-add" aria-label="Добавить своё" onClick={()=>setAdding(true)}><Icon name="plus"/>Своё</button>}
  </div>
  {adding&&<div className="pick-add"><Input autoFocus aria-label="Добавить своё" placeholder="Например, керамика" value={text} maxLength={120} onChange={e=>setText(e.target.value)} onKeyDown={e=>{if(e.key==='Enter'){e.preventDefault();add();}else if(e.key==='Escape'){e.preventDefault();setText('');setAdding(false);}}}/><Button variant="secondary" size="sm" disabled={!text.trim()} onClick={add}>Добавить</Button></div>}
  {skills.length>0&&<div className="field prof-field"><span className="label" id={id+'-sure'}>Получается уверенно</span><div className="pick prof-pick-sm" role="group" aria-labelledby={id+'-sure'}>{skills.map(tag=><button key={tag.label} type="button" className={tag.level==='sure'?'is-on':undefined} aria-pressed={tag.level==='sure'} onClick={()=>onChange(tags.map(item=>item===tag?{...item,level:item.level==='sure'?'learn':'sure'}:item))}>{tag.label}</button>)}</div></div>}
  {dirty&&<div className="actions"><Button variant={primary?'primary':'secondary'} loading={busy} onClick={onSave}>Сохранить</Button></div>}
 </section>;
}

function ContactsCard({contacts}:{contacts:Profile['contacts']}){
 const [changing,setChanging]=useState(false);
 return <section className="card prof-contacts">
  <div className="row prof-card-head"><h2 className="h3">Контакты</h2><Button variant="ghost" size="sm" aria-expanded={changing} onClick={()=>setChanging(v=>!v)}>{changing?'Отмена':'Изменить почту'}</Button></div>
  {contacts.length?<div className="rows">{contacts.map(contact=><div className="rowi" key={contact.type+contact.value}><span className="st st-ok" role="img" aria-label="Подтверждено"><Icon name="check"/></span><div className="grow"><span className="rowi-title">{contact.value}</span><span className="meta">{contact.type==='email'?'Почта':contact.type==='phone'?'Телефон':contact.type}</span></div></div>)}</div>:<p className="p">Подтверждённые контакты появятся после входа.</p>}
  {changing&&<ContactChangePanel/>}
 </section>;
}

/** «Пауза» applies at once, like the notification toggles (no save button on the board). A failed save puts the switch back. */
function PauseCard({draft,saved,change,busy,save}:{draft:ProfileUpdate;saved:ProfileUpdate;change:<K extends keyof ProfileUpdate>(key:K,value:ProfileUpdate[K])=>void;busy:boolean;save:(patch:Partial<ProfileUpdate>,message:string)=>Promise<boolean|null>}){
 const id=useId(),now=today(),soon=addDays(now,21),later=addDays(now,42);
 const paused=draft.lifecycle==='paused',until=draft.paused_until??null;
 const [custom,setCustom]=useState(()=>!!until&&until!==soon&&until!==later);
 async function apply(lifecycle:'active'|'paused',next:string|null,message:string){
  const before={lifecycle:saved.lifecycle,until:saved.paused_until??null};
  change('lifecycle',lifecycle);change('paused_until',next);
  if(await save({lifecycle,paused_until:lifecycle==='paused'?next:null},message)===null){change('lifecycle',before.lifecycle);change('paused_until',before.until);}
 }
 const options:[string,string|null][]=[[`До ${dayMonth(soon)}`,soon],[`До ${dayMonth(later)}`,later],['Пока не включу',null]];
 return <section className="card">
  <div className="set-row"><div className="grow"><b>Пока не приглашать на новые занятия</b><span className="meta">Место в группе сохранится</span></div><button type="button" className={'toggle'+(paused?' is-on':'')} aria-pressed={paused} aria-label="Пока не приглашать на новые занятия" disabled={busy} onClick={()=>{if(paused){setCustom(false);void apply('active',null,'Пауза выключена');}else void apply('paused',null,'Пауза включена');}}/></div>
  {paused&&<div className="field prof-pause-until"><span className="label" id={id}>До какого числа</span>
   <div className="pick" role="group" aria-labelledby={id}>
    {options.map(([label,value])=>{const on=!custom&&until===value;return <button key={label} type="button" className={on?'is-on':undefined} aria-pressed={on} disabled={busy} onClick={()=>{setCustom(false);if(!on)void apply('paused',value,'Сохранено');}}>{label}</button>;})}
    <button type="button" className={custom?'is-on':undefined} aria-pressed={custom} disabled={busy} onClick={()=>setCustom(true)}>{custom&&until?`До ${dayMonth(until)}`:'Другая дата'}</button>
   </div>
   {custom&&<DatePicker label="Выбери дату" value={until??''} onChange={value=>{if(value&&value!==until)void apply('paused',value,'Сохранено');}} min={now}/>}
  </div>}
 </section>;
}
