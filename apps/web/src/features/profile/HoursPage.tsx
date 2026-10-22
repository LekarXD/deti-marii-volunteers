import {useId,useMemo,useState,type CSSProperties} from 'react';
import {useQuery} from '@tanstack/react-query';
import {Link,useSearchParams} from 'react-router-dom';
import {ApiError} from '../../api/transport';
import {keys} from '../../api/keys';
import {Button,Dialog,EmptyState,ErrorState,Icon,LoadingState,type IconName} from '../../ui';
import {DobroMyPath} from '../dobro';
import {usePersonalSchedule} from '../activities/participationApi';
import {readPreparation} from '../followups/api';
import {assignmentWhen,homeScheduleRange,upcomingAssignments} from '../home/model';
import {CertificateForm} from './DocumentsPage';
import {Hours,Prize,PrizeRequest,useHours,useProfileList,useProfileCommand,usePrizePhoto,classesLabel,dayMonth,hoursLabel,moscowDay,monthName,monthYear,pointsDelta,pointsLabel,prizeLabels,shortHours,today} from './api';
import './profile.css';

/** The nearest confirmed занятие of a volunteer who has not been to one yet. */
type FirstClass={id:string;when:string;day:string;marker?:string}|null;
const failureText=(error:unknown)=>error instanceof Error&&error.message?error.message:'Не получилось. Проверь соединение и попробуй ещё раз.';

export function HoursPage(){
 const query=useHours();
 if(query.isPending)return <LoadingState label="Загружаем твой путь…"/>;
 if(query.error)return query.error instanceof ApiError&&query.error.code==='verified_identity_required'?<EmptyState title="Подтверди почту" action={<Link to="/login?next=/hours" className="btn btn-primary">Войти</Link>}/>:<ErrorState error={query.error} retry={()=>void query.refetch()}/>;
 return query.data.level.title?<PathPage hours={query.data} first={null}/>:<NewbiePath hours={query.data}/>;
}

/** Only a newbie needs the schedule: the hero names the first занятие and leads to its preparation. */
function NewbiePath({hours}:{hours:Hours}){
 const [now]=useState(Date.now),{from,to}=homeScheduleRange(now),schedule=usePersonalSchedule(from,to,'active');
 const items=schedule.data?.pages.flatMap(page=>page.items??[])??[];
 // Cursor order is by UUID, so the nearest занятие is known only once every page is loaded.
 const complete=!schedule.isPending&&!schedule.hasNextPage&&!schedule.isError;
 const next=complete?upcomingAssignments(items,now).find(item=>item.status==='confirmed'):undefined;
 const preparation=useQuery({queryKey:keys.detail('assignment-preparation',next?.id??''),queryFn:({signal})=>readPreparation(next!.id,signal),enabled:!!next,staleTime:0});
 const contacts=preparation.data?.contacts??[],marker=(contacts.find(contact=>contact.role==='Ведущий')??contacts.find(contact=>contact.role==='Координатор'))?.display_name.trim().split(/\s+/)[0];
 const when=next?assignmentWhen(next,now).date:'';
 const first=next?{id:next.id,when:when.charAt(0).toUpperCase()+when.slice(1),day:dayMonth(new Intl.DateTimeFormat('en-CA',{timeZone:next.timezone,year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date(next.starts_at))),marker:marker||undefined}:null;
 return <PathPage hours={hours} first={first}/>;
}

function PathPage({hours,first}:{hours:Hours;first:FirstClass}){
 const [params,setParams]=useSearchParams(),[docOpen,setDocOpen]=useState(false),sheetId=useId();
 const {level}=hours,newbie=!level.title,tab=params.get('tab')==='points'?'points':'path';
 const next=!newbie&&level.next_title&&level.next_minutes?{title:level.next_title,minutes:level.next_minutes}:null;
 const sub=newbie?(first?`${first.when}. Часы появятся, когда ${first.marker??'координатор'} отметит занятие.`:'Часы появятся после первого занятия.'):`${hoursLabel(hours.total_minutes)} помощи, ${classesLabel(hours.confirmed_assignments)}`;
 const tabs=[['path','Путь'],['points','Баллы и призы']] as const;
 return <div className="path-page">
  <div className="page-head"><h1 className="h1">Мой путь</h1><Link className="quiet-link" to="/profile">Профиль</Link></div>
  <section className="card-hero">
   <div className="hero-grid">
    <div className="hero-copy">
     <p className="eyebrow">Мой уровень</p>
     <h2 className="hero-title">{level.title??'Первое занятие впереди'}</h2>
     <p className="hero-sub">{sub}</p>
     {next&&<div className="lvl-box lvl">
      <div className="lvl-row"><b>До «{next.title}»</b><span className="strong">осталось {hoursLabel(next.minutes-hours.total_minutes,true)}</span></div>
      <div className="bar" role="progressbar" aria-label={`До уровня «${next.title}»`} aria-valuemin={0} aria-valuemax={next.minutes} aria-valuenow={Math.min(Math.max(hours.total_minutes,0),next.minutes)}><i style={{width:`${Math.min(100,Math.max(0,hours.total_minutes)/next.minutes*100)}%`}}/></div>
     </div>}
     <div className="actions">{newbie
      ?<Link className="btn btn-primary btn-lg" to={first?`/my/assignments/${first.id}/preparation`:'/my/schedule'}>Подготовиться к первому занятию</Link>
      :<Button size="lg" aria-expanded={docOpen} aria-controls={sheetId} onClick={()=>setDocOpen(!docOpen)}><Icon name="download"/>Справка о часах</Button>}</div>
    </div>
    <span className="hero-art" aria-hidden="true"><Icon name="award"/></span>
   </div>
  </section>
  {!newbie&&docOpen&&<section className="sheet path-sheet" id={sheetId} aria-labelledby={sheetId+'-title'}>
   <div className="sheet-head"><h2 className="h3" id={sheetId+'-title'}>Справка о часах</h2><button type="button" className="iconbtn-soft" aria-label="Закрыть" onClick={()=>setDocOpen(false)}><Icon name="x"/></button></div>
   <CertificateForm action="download" extra={<Link className="btn btn-ghost" to="/hours/documents">Мои документы</Link>}/>
  </section>}
  <DobroMyPath/>
  <div className="tabs path-tabs" role="tablist" aria-label="Мой путь">{tabs.map(([key,label])=><button key={key} type="button" role="tab" id={`path-tab-${key}`} aria-controls={`path-panel-${key}`} aria-selected={tab===key} className={tab===key?'is-on':undefined} onClick={()=>setParams(current=>{current.set('tab',key);return current;},{replace:true})}>{label}</button>)}</div>
  {tab==='path'
   ?<div role="tabpanel" id="path-panel-path" aria-labelledby="path-tab-path"><LevelLadder hours={hours}/><Milestones hours={hours} first={first}/>{!newbie&&<Activity entries={hours.entries}/>}<HoursList entries={hours.entries}/>{hours.gratitudes.length>0&&<Thanks gratitudes={hours.gratitudes}/>}</div>
   :<div role="tabpanel" id="path-panel-points" aria-labelledby="path-tab-points"><PointsPanel points={hours.points} entries={hours.entries}/></div>}
 </div>;
}

/** Levels, thresholds and the current step come from the server; the client only lays them out. */
function LevelLadder({hours}:{hours:Hours}){
 const {level}=hours,next=level.steps.find(step=>!step.reached);
 return <section className="path-first"><div className="card path-ladder">{level.steps.map((step,index)=>{const isNext=step===next&&step.minutes!=null;return <div className={'ladder-row'+(step.current?' current':'')} key={step.key} aria-current={step.current?'step':undefined}>
  <span className={'ladder-num'+(step.reached?' reached':'')}>{index+1}</span>
  <div className="grow"><b>{step.title}</b><span className="meta">{step.minutes==null?'Первое занятие':hoursLabel(step.minutes)}</span>
   {isNext&&step.minutes!=null&&<><span className="bar" role="progressbar" aria-label={`До уровня «${step.title}»`} aria-valuemin={0} aria-valuemax={step.minutes} aria-valuenow={Math.min(Math.max(hours.total_minutes,0),step.minutes)}><i style={{width:`${Math.min(100,Math.max(0,hours.total_minutes)/step.minutes*100)}%`}}/></span><span className="p">Осталось {hoursLabel(step.minutes-hours.total_minutes,true)}</span></>}
  </div>
  {step.current&&<span className="here">Ты здесь</span>}
 </div>;})}</div></section>;
}

const mileIcons:Record<string,IconName>={first:'heart',month:'flame',ten:'star',six_months:'award',year:'award'};
const mileTints=['r-o','r-y','r-g','r-v','r-b'];
/** Shifts a calendar day by whole months; a missing day rolls to the 1st of the next month, as on the server. */
function addMonths(day:string,months:number){const [year,month,date]=day.split('-').map(Number),target=new Date(Date.UTC(year,month-1+months,1)),last=new Date(Date.UTC(target.getUTCFullYear(),target.getUTCMonth()+1,0)).getUTCDate();if(date>last)target.setUTCMonth(target.getUTCMonth()+1);else target.setUTCDate(date);return target.toISOString().slice(0,10);}
/** First and tenth занятие with confirmed minutes, counted per assignment like the server does. */
function classDays(entries:Hours['entries']){const byAssignment=new Map<string,{minutes:number;day:string}>();for(const entry of entries){if(!entry.assignment_id)continue;const current=byAssignment.get(entry.assignment_id);byAssignment.set(entry.assignment_id,{minutes:(current?.minutes??0)+entry.delta_minutes,day:current&&current.day<entry.service_date?current.day:entry.service_date});}const days=[...byAssignment.values()].filter(item=>item.minutes>0).map(item=>item.day).sort();return {first:days[0]??null,tenth:days[9]??null};}
function mileNote(item:Hours['achievements'][number],state:'done'|'next'|'lock',days:ReturnType<typeof classDays>,first:FirstClass){
 const anniversary=item.key==='six_months'?6:item.key==='year'?12:0,start=days.first;
 if(state==='done')return item.key==='first'&&start?dayMonth(start):item.key==='ten'&&days.tenth?dayMonth(days.tenth):anniversary&&start?dayMonth(addMonths(start,anniversary)):'';
 if(state==='next')return item.key==='first'?first?.day??'':item.key==='ten'?`ещё ${classesLabel(Math.max(item.target-item.progress,1))}`:anniversary&&start?dayMonth(addMonths(start,anniversary)):'';
 return anniversary&&start?monthYear(addMonths(start,anniversary)):'';
}
function Milestones({hours,first}:{hours:Hours;first:FirstClass}){
 const days=useMemo(()=>classDays(hours.entries),[hours.entries]),nextKey=hours.achievements.find(item=>!item.earned)?.key;
 return <section className="sec"><div className="sec-head"><h2 className="h2">Вехи</h2></div><div className="card"><div className="miles">{hours.achievements.map((item,index)=>{
  const state=item.earned?'done':item.key===nextKey?'next':'lock',note=mileNote(item,state,days,first);
  // The next ring always shows some orange, as on the board, even before the first step of progress.
  const pct=Math.max(12,Math.round(Math.min(1,Math.max(0,item.progress/Math.max(item.target,1)))*100));
  return <div key={item.key} className={'mile'+(state==='next'?' next':state==='lock'?' lock':'')} style={state==='next'?{'--mile-pct':`${pct}%`} as CSSProperties:undefined}>
   <span className={'ring'+(state==='done'?' '+mileTints[index%mileTints.length]:'')} aria-hidden="true"><Icon name={state==='lock'?'lock':mileIcons[item.key]??'award'}/></span>
   <b>{item.title}</b>{note&&<span className="meta">{note}</span>}
   <span className="sr-only">{state==='done'?'Получено':state==='next'?'Следующая веха':'Впереди'}</span>
  </div>;})}</div></div></section>;
}

const monthsShort=['янв','фев','мар','апр','май','июн','июл','авг','сен','окт','ноя','дек'];
const DAY=86400000,WEEKS=26;
/** 26 weeks by 7 weekdays ending with the current Moscow week; intensity follows confirmed minutes of the day. */
function heatmap(entries:Hours['entries'],todayIso:string){
 const net=new Map<string,number>();for(const entry of entries)net.set(entry.service_date,(net.get(entry.service_date)??0)+entry.delta_minutes);
 const base=Date.parse(todayIso+'T00:00:00Z'),start=base-((new Date(base).getUTCDay()+6)%7+(WEEKS-1)*7)*DAY,iso=(time:number)=>new Date(time).toISOString().slice(0,10);
 const cells=[];
 for(let row=0;row<7;row++)for(let column=0;column<WEEKS;column++){const time=start+(column*7+row)*DAY,day=iso(time),minutes=net.get(day)??0,future=time>base;cells.push({day,minutes,future,level:future?'is-future':minutes<=0?'':minutes<=60?'h1':minutes<=240?'h2':minutes<=360?'h3':'h4'});}
 // A week belongs to the month of its Sunday, so a label starts at the week holding the 1st.
 const months:{month:number;start:number;span:number}[]=[];
 for(let column=0;column<WEEKS;column++){const month=new Date(start+(column*7+6)*DAY).getUTCMonth(),last=months.at(-1);if(last&&last.month===month)last.span++;else months.push({month,start:column,span:1});}
 return {cells,months:months.filter((item,index)=>index>0||item.span>=3)};
}
function Activity({entries}:{entries:Hours['entries']}){
 const {cells,months}=useMemo(()=>heatmap(entries,today()),[entries]);
 return <section className="sec"><div className="sec-head"><h2 className="h2">Активность за полгода</h2></div><div className="card">
  <div className="heat-months path-heat-months" aria-hidden="true">{months.map(item=><span key={item.start} style={{gridColumn:`${item.start+1} / span ${item.span}`}}><span className="m-full">{monthName(item.month)}</span><span className="m-short">{monthsShort[item.month]}</span></span>)}</div>
  <div className="heat" role="img" aria-label="Занятия по неделям за полгода">{cells.map(cell=><i key={cell.day} className={cell.level||undefined} title={cell.future||!cell.minutes?undefined:`${dayMonth(cell.day)}: ${shortHours(cell.minutes)}`}/>)}</div>
 </div></section>;
}

function HoursList({entries}:{entries:Hours['entries']}){
 const rows=entries.filter(entry=>entry.delta_minutes!==0),[all,setAll]=useState(false),shown=all?rows:rows.slice(0,4);
 return <section className="sec"><div className="sec-head"><h2 className="h2">Часы</h2></div><div className="card">{rows.length?<>
  <div className="rows">{shown.map(entry=><div className="rowi" key={entry.id}>
   {entry.delta_minutes>0?<span className="st st-ok" role="img" aria-label="Засчитано"><Icon name="check"/></span>:<span className="st st-off" role="img" aria-label="Исправление"><Icon name="edit"/></span>}
   <div className="grow"><span className="rowi-title">{entry.title}</span><span className="meta">{dayMonth(entry.service_date)}</span></div>
   <span className="rowi-end"><span className="hours-num">{shortHours(entry.delta_minutes)}</span></span>
  </div>)}</div>
  {rows.length>4&&<Button variant="ghost" className="path-more" aria-expanded={all} onClick={()=>setAll(!all)}>{all?'Свернуть':`Показать все (${rows.length})`}</Button>}
 </>:<p className="p path-empty">Здесь появятся часы после первого занятия.</p>}</div></section>;
}

/** «…». with the full stop after the closing quote, as Russian typography wants; ! and ? stay inside. */
const quote=(text:string)=>{const bare=text.trim().replace(/\.+$/,'').replace(/^[«"„]+|[»"“]+$/g,'').trim().replace(/\.+$/,'');return /[!?…]$/.test(bare)?`«${bare}»`:`«${bare}».`;};
function Thanks({gratitudes}:{gratitudes:Hours['gratitudes']}){
 return <section className="sec"><div className="sec-head"><h2 className="h2">Спасибо от команды</h2></div><div className="card path-thanks">{gratitudes.map(item=><figure key={item.id}>
  <blockquote className="thanks">{quote(item.text)}</blockquote>
  <figcaption className="meta">{item.author}, {dayMonth(moscowDay(item.created_at))}</figcaption>
 </figure>)}</div></section>;
}

const prizeTints=['art-o','art-y','art-v','art-g'];
/** Minutes per attended занятие keyed like the server's points history (title and first service day). */
function attendanceMinutes(entries:Hours['entries']){
 const groups=new Map<string,{title:string;day:string;minutes:number}>();
 for(const entry of entries){if(entry.source_kind!=='attendance'||!entry.assignment_id)continue;const current=groups.get(entry.assignment_id);groups.set(entry.assignment_id,{title:current?.title??entry.title,day:current&&current.day<entry.service_date?current.day:entry.service_date,minutes:(current?.minutes??0)+entry.delta_minutes});}
 const byKey=new Map<string,number>();for(const group of groups.values()){const key=group.title+'|'+group.day;byKey.set(key,(byKey.get(key)??0)+group.minutes);}
 return byKey;
}
const durationText=(minutes:number)=>minutes%60===0?hoursLabel(minutes):shortHours(minutes);
function PointsPanel({points,entries}:{points:Hours['points'];entries:Hours['entries']}){
 const prizes=useProfileList<Prize>('prizes','/prizes'),requests=useProfileList<PrizeRequest>('prize-requests','/me/prize-requests'),[choice,setChoice]=useState<Prize|null>(null),[all,setAll]=useState(false);
 const minutes=useMemo(()=>attendanceMinutes(entries),[entries]);
 const own=(requests.data??[]).filter(row=>row.state!=='cancelled'),shown=all?own:own.slice(0,4),waiting=new Set(own.filter(row=>row.state==='requested').map(row=>row.prize_id));
 const note=points.balance<0?'Баланс стал меньше нуля после исправления часов. Новые заявки откроются, когда он снова станет больше нуля.':points.reserved>0?`Ещё ${pointsLabel(points.reserved)} отложены под заявки`:'Можно потратить на призы';
 return <>
  <section className="path-first"><div className="card stack path-points">
   <span className="pts-big">{pointsLabel(points.balance)}</span>
   <p className="p path-note">{note}</p>
   <details className="how"><summary><Icon name="chevron-down"/>Как начисляются баллы</summary><p>10 баллов за час подтверждённой помощи. На отдельных занятиях баллы за час умножаются на 1,5. За знакомство с фондом — 100 баллов один раз.</p></details>
  </div></section>
  <section className="sec"><div className="sec-head"><h2 className="h2">Призы</h2></div>
   {prizes.isPending?<LoadingState label="Загружаем призы…"/>:prizes.error?<ErrorState error={prizes.error} retry={()=>void prizes.refetch()}/>:prizes.data?.length
    ?<div className="prizes">{prizes.data.map((prize,index)=><PrizeCard key={prize.id} prize={prize} tint={prizeTints[index%prizeTints.length]} balance={points.balance} canRequest={points.can_request} waiting={waiting.has(prize.id)} choose={()=>setChoice(prize)}/>)}</div>
    :<div className="card"><p className="p path-empty">Призы появятся здесь, когда фонд их добавит.</p></div>}
  </section>
  {own.length>0&&<section className="sec"><div className="sec-head"><h2 className="h2">Мои заявки</h2></div><div className="card">
   <div className="rows">{shown.map(row=><PrizeRequestRow key={row.id} row={row}/>)}</div>
   {own.length>4&&<Button variant="ghost" className="path-more" aria-expanded={all} onClick={()=>setAll(!all)}>{all?'Свернуть':`Показать все (${own.length})`}</Button>}
  </div></section>}
  {points.history.length>0&&<section className="sec"><details className="how path-history"><summary className="h3"><Icon name="chevron-down"/>История баллов</summary><div className="card">{points.history.map((item,index)=><div className="hist-row" key={index}>
   <div className="grow"><span className="rowi-title">{item.kind==='prize'?`Приз: ${lowerFirst(item.title)}`:item.title}</span><span className="meta">{dayMonth(item.on)}{item.kind==='attendance'&&minutes.get(item.title+'|'+item.on)?`, ${durationText(minutes.get(item.title+'|'+item.on)!)}`:''}{item.state==='requested'?', в заявке':''}</span></div>
   {item.multiplier!=null&&item.multiplier>1&&<span className="pts-tag">×{String(item.multiplier).replace('.',',')}</span>}
   <b>{pointsDelta(item.points)}</b>
  </div>)}</div></details></section>}
  <PrizeDialog prize={choice} close={()=>setChoice(null)}/>
 </>;
}
const lowerFirst=(text:string)=>text.length>1&&text[1]===text[1].toLowerCase()?text.charAt(0).toLowerCase()+text.slice(1):text;

/** Coordinator showcase thumbnail; the volunteer cards below use their own picture slot. */
export function PrizeArt({prize,staff=false,thumb=false}:{prize:Prize;staff?:boolean;thumb?:boolean}){const photo=usePrizePhoto(prize,staff);return photo.data?<img className={thumb?'profile-prize-thumb':'profile-prize-photo'} src={photo.data} alt=""/>:<span className="art art-y" aria-hidden="true"><Icon name="heart"/></span>;}
function PrizeCard({prize,tint,balance,canRequest,waiting,choose}:{prize:Prize;tint:string;balance:number;canRequest:boolean;waiting:boolean;choose:()=>void}){
 const photo=usePrizePhoto(prize),titleId=useId(),short=prize.price_points-balance;
 return <div className="prize">
  {photo.data?<img className="prize-pic" src={photo.data} alt=""/>:<span className={'prize-pic '+tint} aria-hidden="true"><Icon name="heart"/></span>}
  <div className="prize-body">
   <b id={titleId}>{prize.title}</b>
   {prize.description&&<span className="p">{prize.description}</span>}
   <div className="prize-foot"><span className="price">{pointsLabel(prize.price_points)}</span>
    {waiting?<span className="tag">В заявке</span>:prize.stock<1?<span className="tag">Закончился</span>:canRequest&&short<=0?<Button variant="secondary" size="sm" aria-describedby={titleId} onClick={choose}>Выбрать</Button>:<span className="short">Не хватает {pointsLabel(Math.max(short,1))}</span>}
   </div>
  </div>
 </div>;
}
function PrizeDialog({prize,close}:{prize:Prize|null;close:()=>void}){
 const save=useProfileCommand<PrizeRequest>('/me/prize-requests');
 return <Dialog open={!!prize} onClose={()=>!save.isPending&&close()} title="Выбрать приз?" className="path-dlg" footer={<><Button loading={save.isPending} onClick={()=>void save.mutateAsync({prize_id:prize!.id}).then(()=>{save.reset();close();}).catch(()=>{})}>Отправить заявку</Button><Button variant="ghost" onClick={()=>{save.reset();close();}}>Отмена</Button></>}>
  {prize&&<><p className="p path-dlg-lead">{prize.title}, {pointsLabel(prize.price_points)}.</p><p className="p">Баллы отложим, пока координатор не выдаст приз. Заявку можно отменить до выдачи.</p></>}
  {save.error&&<p className="path-alert" role="alert">{failureText(save.error)}</p>}
 </Dialog>;
}
function PrizeRequestRow({row}:{row:PrizeRequest}){
 const cancel=useProfileCommand<PrizeRequest>(`/me/prize-requests/${row.id}/cancel`),pending=row.state==='requested',issued=row.state==='issued',price=pointsLabel(row.points);
 const meta=pending?`${price}, заявка у координатора`:issued?`${price}, выдан ${dayMonth(moscowDay(row.updated_at))}`:`${price}, ${(prizeLabels[row.state]??row.state).toLowerCase()}`;
 return <div className="rowi">
  <span className={'st '+(issued?'st-ok':pending?'st-wait':'st-off')} role="img" aria-label={prizeLabels[row.state]??row.state}><Icon name={issued?'check':pending?'clock':'x'}/></span>
  <div className="grow"><span className="rowi-title">{row.prize_title}</span><span className="meta">{meta}</span>{row.reason&&!pending&&<span className="meta">{row.reason}</span>}{cancel.error&&<span className="path-alert" role="alert">{failureText(cancel.error)}</span>}</div>
  {pending&&<span className="rowi-end"><Button variant="ghost" size="sm" disabled={cancel.isPending} onClick={()=>cancel.mutate({expected_version:row.version})}>Отменить заявку</Button></span>}
 </div>;
}
