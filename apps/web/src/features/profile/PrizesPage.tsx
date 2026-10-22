import {useRef,useState,type RefObject} from 'react';
import {useQueryClient} from '@tanstack/react-query';
import {api,getSession} from '../../api/transport';
import {keys} from '../../api/keys';
import {Button,ErrorState,Icon,LoadingState,SectionTabs,cx,type IconName} from '../../ui';
import {volunteersTabs} from '../../app/sectionTabs';
import {type Asset,type Prize,type PrizeRequest,pointsLabel,usePrizePhoto,useProfileCommand,useProfileList} from './api';
import './prizes.css';

/** Prizes board (22 Oct): requests waiting to be issued and the showcase on one screen. */
const arts:[string,IconName][]=[['art-o','palette'],['art-v','mask'],['art-y','image'],['art-p','heart'],['art-g','users'],['art-b','star']];
const artOf=(id:string):[string,IconName]=>arts[[...id].reduce((sum,char)=>sum+char.charCodeAt(0),0)%arts.length];
const tones=['ph-o','ph-g','ph-b','ph-p','ph-v'];
const toneOf=(id:string)=>tones[[...id].reduce((sum,char)=>sum+char.charCodeAt(0),0)%tones.length];
const initials=(name:string)=>name.trim().split(/\s+/).filter(part=>/^\p{L}/u.test(part)).slice(0,2).map(part=>part[0]).join('').toUpperCase();
const firstName=(name:string)=>name.trim().split(/\s+/).find(part=>/^\p{L}/u.test(part))??name;
const requestsWord=(n:number)=>{const a=n%10,b=n%100;return `${n} ${a===1&&b!==11?'заявка':a>=2&&a<=4&&(b<12||b>14)?'заявки':'заявок'}`;};
const dayKey=(value:Date)=>value.toLocaleDateString('sv-SE',{timeZone:'Europe/Moscow'});
function whenLabel(iso:string){const at=new Date(iso),today=new Date(),yesterday=new Date(Date.now()-864e5);return dayKey(at)===dayKey(today)?'сегодня':dayKey(at)===dayKey(yesterday)?'вчера':at.toLocaleDateString('ru',{day:'numeric',month:'long',timeZone:'Europe/Moscow'});}

const NO_PRIZE:Prize={id:'',title:'',description:'',price_points:0,stock:0,visible:false,version:0,photo_asset_id:null};

function PrizeArt({prize,large=false}:{prize:Prize;large?:boolean}){const photo=usePrizePhoto(prize,true),[art,icon]=artOf(prize.id);return photo.data?<img className={large?'prz-photo':'prz-thumb'} src={photo.data} alt=""/>:<span className={cx('art',art,large&&'art-lg prz-art-lg',!large&&'prz-art')} aria-hidden="true"><Icon name={icon}/></span>;}

export function PrizesPage(){
 const requests=useProfileList<PrizeRequest>('review-prize-requests','/coord/prize-requests'),catalog=useProfileList<Prize>('review-prizes','/coord/prizes');
 const [flash,setFlash]=useState(''),[editing,setEditing]=useState<string|null>(null);const form=useRef<HTMLElement>(null);
 const open=(id:string)=>{setEditing(id);setFlash('');setTimeout(()=>form.current?.scrollIntoView({behavior:'smooth',block:'start'}),0);};
 const prizes=catalog.data??[],queue=(requests.data??[]).filter(row=>row.state==='requested').sort((a,b)=>a.created_at.localeCompare(b.created_at));
 const byPrize=new Map<string,number>();for(const row of queue)byPrize.set(row.prize_id,(byPrize.get(row.prize_id)??0)+1);
 const prizeOf=(row:PrizeRequest)=>prizes.find(prize=>prize.id===row.prize_id);
 return <div className="prizes-page">
  <SectionTabs label="Волонтёры" tabs={volunteersTabs} actions={<Button variant="secondary" onClick={()=>open('new')}><Icon name="plus"/>Новый приз</Button>}/>
  {flash&&<div className="done-note" role="status"><Icon name="check"/>{flash}</div>}
  <section aria-labelledby="prz-queue">
   <div className="sec-head prz-queue-head"><h2 className="h2" id="prz-queue">Ждут выдачи</h2>{queue.length>0&&<span className="stage-n hot">{queue.length}</span>}</div>
   {requests.isPending?<LoadingState label="Загружаем заявки…"/>:requests.error?<ErrorState error={requests.error} retry={()=>void requests.refetch()}/>:queue.length?<div className="card prz-queue">{queue.map(row=><RequestRow key={row.id} row={row} prize={prizeOf(row)} done={setFlash}/>)}</div>:<div className="card empty-note"><p className="h3">Всё выдано</p></div>}
  </section>
  <section className="section" aria-labelledby="prz-shop">
   <div className="sec-head"><h2 className="h2" id="prz-shop">Витрина</h2></div>
   {editing&&<PrizeForm key={editing} anchor={form} prize={prizes.find(prize=>prize.id===editing)} close={()=>setEditing(null)} saved={()=>{setEditing(null);setFlash('Приз сохранён');}}/>}
   {catalog.isPending?<LoadingState label="Загружаем витрину…"/>:catalog.error?<ErrorState error={catalog.error} retry={()=>void catalog.refetch()}/>:<div className="grid-3 prz-grid">
    {prizes.map(prize=><PrizeCard key={prize.id} prize={prize} waiting={byPrize.get(prize.id)??0} edit={()=>open(prize.id)}/>)}
    <button type="button" className="prz-add" onClick={()=>open('new')}><Icon name="plus"/>Новый приз</button>
   </div>}
  </section>
 </div>;
}

function RequestRow({row,prize,done}:{row:PrizeRequest;prize?:Prize;done:(text:string)=>void}){
 const [declining,setDeclining]=useState(false),[reason,setReason]=useState(''),save=useProfileCommand<PrizeRequest>(`/coord/prize-requests/${row.id}/decision`,'POST',row.version);
 const own=row.user_id===getSession()?.user_id,name=row.display_name||'Волонтёр';
 const issue=()=>void save.mutateAsync({expected_version:row.version,decision:'issued',reason:''}).then(()=>done(`${row.prize_title}: выдано, ${firstName(name)} получит сообщение`)).catch(()=>{});
 const decline=()=>void save.mutateAsync({expected_version:row.version,decision:'rejected',reason}).then(()=>done(`Заявка отклонена, баллы вернулись ${firstName(name)}`)).catch(()=>{});
 return <div className="prz-row">
  <div className="prz-row-main">
   {prize?<PrizeArt prize={prize}/>:<span className="art art-y prz-art" aria-hidden="true"><Icon name="award"/></span>}
   <span className="prz-what"><span className="h3">{row.prize_title}</span><span className="meta">{pointsLabel(row.points)}</span></span>
   <span className="person"><span className={cx('ph ph-sm',toneOf(row.user_id))} aria-hidden="true">{initials(name)}</span><span style={{minWidth:0}}><span className="person-name">{name}</span><span className="meta">{whenLabel(row.created_at)}</span></span></span>
   <span className="prz-actions">{own?<span className="meta">Выдаст другой сотрудник</span>:<><Button variant="secondary" size="sm" disabled={save.isPending} onClick={issue}>Выдать</Button><Button variant="ghost" size="sm" aria-expanded={declining} onClick={()=>{setDeclining(!declining);setReason('');}}>Отклонить</Button></>}</span>
  </div>
  {declining&&<div className="prz-decline"><label className="sr-only" htmlFor={`prz-reason-${row.id}`}>Причина отказа</label><input id={`prz-reason-${row.id}`} className="input" placeholder="Почему отказываем, увидит волонтёр" value={reason} maxLength={4000} onChange={e=>setReason(e.target.value)}/><Button variant="danger" size="sm" disabled={reason.trim().length<3||save.isPending} onClick={decline}>Отклонить и вернуть баллы</Button></div>}
  {save.error&&<ErrorState error={save.error}/>}
 </div>;
}

function PrizeCard({prize,waiting,edit}:{prize:Prize;waiting:number;edit:()=>void}){
 const save=useProfileCommand<Prize>(`/coord/prizes/${prize.id}`,'PUT',prize.version);
 const toggle=()=>save.mutate({expected_version:prize.version,title:prize.title,description:prize.description,price_points:prize.price_points,stock:prize.stock,visible:!prize.visible,photo_asset_id:prize.photo_asset_id??null});
 return <article className="card prz-card">
  <div className="prz-media"><PrizeArt prize={prize} large/>{waiting>0&&<span className="badge prz-badge-end">{requestsWord(waiting)}</span>}{!prize.visible&&<span className="badge badge-quiet prz-badge-start">Скрыт</span>}</div>
  <div className="prz-text"><h3 className="h3">{prize.title}</h3>{prize.description&&<p className="p">{prize.description}</p>}</div>
  <div className="prz-price"><b>{pointsLabel(prize.price_points)}</b><span className={prize.stock>0?'meta':'fill-low'}>{prize.stock>0?`осталось ${prize.stock}`:'закончился'}</span></div>
  <div className="prz-foot"><span className="toggle-line"><button type="button" className={cx('toggle',prize.visible&&'is-on')} role="switch" aria-checked={prize.visible} aria-label={`Показывать волонтёрам: ${prize.title}`} disabled={save.isPending} onClick={toggle}/>Видно волонтёрам</span><Button variant="ghost" size="sm" onClick={edit}>Изменить</Button></div>
  {save.error&&<ErrorState error={save.error}/>}
 </article>;
}

function PrizeForm({anchor,prize,close,saved}:{anchor:RefObject<HTMLElement>;prize?:Prize;close:()=>void;saved:()=>void}){
 const [draft,setDraft]=useState({title:prize?.title??'',description:prize?.description??'',price:String(prize?.price_points??''),stock:String(prize?.stock??'')}),[file,setFile]=useState<File|null>(null),[preview,setPreview]=useState<string>();
 const cache=useQueryClient(),create=useProfileCommand<Prize>('/coord/prizes','POST'),update=useProfileCommand<Prize>(prize?`/coord/prizes/${prize.id}`:'/coord/prizes','PUT',prize?.version),upload=usePrizePhotoUpload(),current=usePrizePhoto(prize??NO_PRIZE,true);
 const price=Number(draft.price),stock=Number(draft.stock),valid=!!draft.title.trim()&&Number.isInteger(price)&&price>=1&&Number.isInteger(stock)&&stock>=0&&draft.stock!=='';
 const busy=create.isPending||update.isPending||upload.busy,error=create.error??update.error;
 const body={title:draft.title.trim(),description:draft.description.trim(),price_points:price,stock,visible:prize?.visible??true};
 const submit=async()=>{try{
  let row=prize?await update.mutateAsync({...body,expected_version:prize.version,photo_asset_id:prize.photo_asset_id??null}):await create.mutateAsync({...body,photo_asset_id:null});
  if(file){const photo=await upload.run(row,file);row=await api<Prize>(`/coord/prizes/${row.id}`,{method:'PUT',body:{...body,expected_version:row.version,photo_asset_id:photo},idempotencyKey:crypto.randomUUID()});await cache.invalidateQueries({queryKey:keys.all('profile-review-prizes')});}
  saved();
 }catch{/* the error shows under the form */}};
 const pick=(chosen:File|undefined)=>{if(!chosen)return;if(chosen.size>5*1024*1024||!['image/png','image/jpeg'].includes(chosen.type)){upload.fail('Выберите PNG или JPEG до 5 МБ');return;}upload.fail(undefined);setFile(chosen);setPreview(URL.createObjectURL(chosen));};
 const shown=preview??current.data;
 return <section ref={anchor} className="form-card prz-form" aria-labelledby="prz-form-title">
  <div className="panel-head"><h3 className="h3" id="prz-form-title">{prize?'Изменить приз':'Новый приз'}</h3><button type="button" className="iconbtn-soft" aria-label="Закрыть" onClick={close}><Icon name="x"/></button></div>
  <div className="prz-form-body">
   <div className={cx('photo-drop',shown&&'has-photo')}><span className={cx('photo-frame',shown&&'filled')} aria-hidden="true">{shown?<img src={shown} alt=""/>:<Icon name="image"/>}</span><label className="btn btn-secondary btn-sm prz-file">{shown?'Заменить фото':'Загрузить фото'}<input type="file" accept="image/png,image/jpeg" onChange={e=>pick(e.target.files?.[0])}/></label></div>
   <div className="form-grid">
    <label className="field full"><span className="label">Название</span><input className="input" value={draft.title} maxLength={200} placeholder="Например, кружка из мастерской" onChange={e=>setDraft({...draft,title:e.target.value})}/></label>
    <label className="field full"><span className="label">Описание</span><textarea className="textarea" value={draft.description} maxLength={4000} onChange={e=>setDraft({...draft,description:e.target.value})}/></label>
    <label className="field"><span className="label">Цена в баллах</span><input className="input" inputMode="numeric" value={draft.price} onChange={e=>setDraft({...draft,price:e.target.value.replace(/\D/g,'')})}/></label>
    <label className="field"><span className="label">Сколько осталось</span><input className="input" inputMode="numeric" value={draft.stock} onChange={e=>setDraft({...draft,stock:e.target.value.replace(/\D/g,'')})}/></label>
   </div>
  </div>
  {upload.error&&<p className="prz-error" role="alert">{upload.error}</p>}
  {error&&<ErrorState error={error}/>}
  <div className="actions"><Button disabled={!valid||busy} loading={busy} onClick={()=>void submit()}>Сохранить приз</Button></div>
 </section>;
}

/** Uploads a prize photo in 1 MB chunks and returns the ready asset id. */
function usePrizePhotoUpload(){
 const cache=useQueryClient(),[busy,setBusy]=useState(false),[error,setError]=useState<string>();
 return {busy,error,fail:setError,run:async(prize:Prize,file:File)=>{setBusy(true);setError(undefined);try{
  const data=await file.arrayBuffer(),digest=await crypto.subtle.digest('SHA-256',data),checksum=Array.from(new Uint8Array(digest)).map(b=>b.toString(16).padStart(2,'0')).join('');
  const intent=await api<Asset>(`/coord/prizes/${prize.id}/photo-intents`,{method:'POST',body:{content_type:file.type,expected_size:file.size,checksum},idempotencyKey:crypto.randomUUID()});
  for(let offset=0;offset<data.byteLength;offset+=1024*1024)await api(`/assets/${intent.id}/upload`,{method:'PATCH',body:data.slice(offset,offset+1024*1024),headers:{'X-Upload-Offset':String(offset),'Content-Type':'application/octet-stream'}});
  const ready=await api<Asset>(`/assets/${intent.id}/complete-upload`,{method:'POST'});if(ready.state!=='ready')throw Error('Фото не прошло проверку');
  await cache.invalidateQueries({queryKey:keys.all('profile-prize-photo')});return ready.id;
 }catch(reason){setError(reason instanceof Error?reason.message:'Не удалось загрузить фото');throw reason;}finally{setBusy(false);}}};
}
