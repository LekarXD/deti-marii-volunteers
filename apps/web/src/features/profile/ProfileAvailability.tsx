import {useId,useState} from 'react';
import {ApiError} from '../../api/transport';
import {Button,ErrorState,Field,Icon,LoadingState,Textarea,useToast} from '../../ui';
import type {components} from '../../api/generated/schema';
import {OwnAvailability,useOwnAvailability,useProfileCommand} from './api';

type Window=components['schemas']['AvailabilityWindowInput'];
type Channel=components['schemas']['SelfAvailabilityCommand']['preferred_channel'];

const days=['Пн','Вт','Ср','Чт','Пт','Сб','Вс'];
const parts=[['Утро','утро',540,720],['День','день',720,1080],['Вечер','вечер',1080,1260]] as const;
const channels:[Channel,string][]=[['email','Почта'],['phone','Телефон'],['telegram','Telegram'],['max','MAX'],['whatsapp','WhatsApp'],['other','Другое']];
const slotKey=(w:Window)=>`${w.weekday}:${w.start_minute}:${w.end_minute}`;
const isSlot=(w:Window)=>parts.some(([, ,start,end])=>w.start_minute===start&&w.end_minute===end);
const sortWindows=(windows:Window[])=>[...windows].sort((a,b)=>a.weekday-b.weekday||a.start_minute-b.start_minute||a.end_minute-b.end_minute);
/** «Ср вечер, Сб утро»: what the grid says, used when the free text is left empty. */
export const describeWindows=(windows:Window[])=>sortWindows(windows).filter(isSlot).map(w=>`${days[w.weekday]} ${parts.find(([, ,start,end])=>w.start_minute===start&&w.end_minute===end)![1]}`).join(', ');

export interface PlacesProps{options:string[];selected:string[];onToggle:(label:string)=>void;dirty:boolean;save:()=>Promise<boolean>;busy:boolean}

/** «Когда свободна»: the week grid and free text write the volunteer's own CRM availability; «Где удобно» are profile picks. */
export function ProfileAvailability({places}:{places:PlacesProps}){
 const query=useOwnAvailability();
 if(query.isPending)return <LoadingState label="Загружаем расписание…"/>;
 if(query.error)return <ErrorState error={query.error} retry={()=>void query.refetch()}/>;
 return <AvailabilityForm key={query.data.volunteer_id||'new'} initial={query.data} places={places}/>;
}

function snapshot(view:OwnAvailability){
 const current=view.availability,windows=sortWindows(current?.windows??[]),summary=current?.summary??'';
 return {windows,summary:summary===describeWindows(windows)?'':summary,channel:(current?.preferred_channel||'email') as Channel,timezone:current?.timezone||'Europe/Moscow'};
}

function AvailabilityForm({initial,places}:{initial:OwnAvailability;places:PlacesProps}){
 const id=useId(),{toast}=useToast();
 const [base,setBase]=useState(()=>snapshot(initial));
 const [windows,setWindows]=useState(base.windows),[summary,setSummary]=useState(base.summary),[channel,setChannel]=useState<Channel>(base.channel);
 const save=useProfileCommand<OwnAvailability>('/me/availability','PUT',initial.version);
 const sorted=sortWindows(windows),text=summary.trim()||describeWindows(sorted);
 const dirty=JSON.stringify({w:sorted.map(slotKey),s:summary.trim(),c:channel})!==JSON.stringify({w:base.windows.map(slotKey),s:base.summary.trim(),c:base.channel});
 const busy=save.isPending||places.busy;
 const toggle=(weekday:number,start_minute:number,end_minute:number)=>setWindows(old=>old.some(w=>w.weekday===weekday&&w.start_minute===start_minute&&w.end_minute===end_minute)?old.filter(w=>!(w.weekday===weekday&&w.start_minute===start_minute&&w.end_minute===end_minute)):[...old,{weekday,start_minute,end_minute}]);
 const channelOptions=channels.filter(([value])=>['email','phone','telegram','other'].includes(value)||value===channel);
 async function submit(){
  let ok=true;
  if(dirty){
   try{const next=await save.mutateAsync({expected_version:initial.version,summary:text,preferred_channel:channel,timezone:base.timezone,windows:sorted});setBase(snapshot(next));}
   catch{ok=false;}
  }
  if(ok&&places.dirty)ok=await places.save();
  if(ok)toast('Сохранено');
 }
 return <div className="card prof-time">
  <h2 className="h3 prof-time-title">Когда свободна</h2>
  <div className="when-grid">
   <span/>{parts.map(([label])=><span key={label} className="label">{label}</span>)}
   {days.map((day,weekday)=><WeekRow key={day} day={day} weekday={weekday} windows={windows} toggle={toggle}/>)}
  </div>
  {places.options.length>0&&<div className="field prof-field"><span className="label" id={id+'-places'}>Где удобно</span><div className="pick" role="group" aria-labelledby={id+'-places'}>{places.options.map(label=>{const on=places.selected.includes(label);return <button key={label} type="button" className={on?'is-on':undefined} aria-pressed={on} onClick={()=>places.onToggle(label)}>{label}</button>;})}</div></div>}
  <div className="field prof-field"><span className="label" id={id+'-channel'}>Как с тобой удобнее связаться</span><div className="pick" role="group" aria-labelledby={id+'-channel'}>{channelOptions.map(([value,label])=><button key={value} type="button" className={channel===value?'is-on':undefined} aria-pressed={channel===value} onClick={()=>setChannel(value)}>{label}</button>)}</div></div>
  <Field className="prof-field" label="Что ещё учесть"><Textarea value={summary} onChange={e=>setSummary(e.target.value)} rows={3} maxLength={4000} placeholder="Например: раз в две недели, после работы"/></Field>
  <div className="row prof-actions"><Button disabled={(!dirty&&!places.dirty)||!text||busy} loading={busy} onClick={()=>void submit()}>Сохранить</Button></div>
  {save.error&&<p className="err" role="alert">{save.error instanceof ApiError&&save.error.status===409?'Расписание изменилось в другом окне. Обнови страницу и отметь снова.':save.error.message}</p>}
 </div>;
}

function WeekRow({day,weekday,windows,toggle}:{day:string;weekday:number;windows:Window[];toggle:(weekday:number,start:number,end:number)=>void}){
 return <>
  <span className="wd">{day}</span>
  {parts.map(([label,lower,start,end])=>{const on=windows.some(w=>w.weekday===weekday&&w.start_minute===start&&w.end_minute===end);return <button key={label} type="button" className={on?'is-on':undefined} aria-pressed={on} aria-label={`${day}, ${lower}`} onClick={()=>toggle(weekday,start,end)}>{on&&<><span className="prof-when-word">Свободна</span><Icon name="check" className="prof-when-mark"/></>}</button>;})}
 </>;
}
