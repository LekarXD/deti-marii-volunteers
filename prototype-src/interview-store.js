// Shared browser demo registry for candidate progress, availability and interviews.
// Stored locally on this origin; no real invitations or reminders are sent.
const INTERVIEW_KEY = 'opora-interviews-v1';
const INTERVIEW_TODAY = '2026-10-21';
const interviewMinutes = text => {const m=/^([01]\d|2[0-3]):([0-5]\d)$/.exec(text||'');return m?Number(m[1])*60+Number(m[2]):NaN;};
const interviewTimeInput = value => {const digits=String(value).replace(/\D/g,'').slice(0,4);return digits.length>2?digits.slice(0,2)+':'+digits.slice(2):digits;};
const interviewTime = n => String(Math.floor(n/60)).padStart(2,'0')+':'+String(n%60).padStart(2,'0');
const interviewFuture = (date,time) => date>INTERVIEW_TODAY||(date===INTERVIEW_TODAY&&time>new Intl.DateTimeFormat('ru-RU',{timeZone:'Europe/Moscow',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).format(new Date()));
const interviewDay = date => scheduleLabel(date,{weekday:'short',day:'numeric',month:'long',year:'numeric'});
const interviewIdentity = person => String(person?.interviewId||person?.email||person?.phone||person?.name||'').trim().toLowerCase();
const interviewDefaults = () => ({
  windows: [
    {id:'thu',date:'2026-10-22',start:'18:00',end:'20:00',duration:30,gap:10,repeat:'weekly',until:'',exceptions:[],where:'Онлайн, Яндекс Телемост',link:'',active:true},
    {id:'fri',date:'2026-10-23',start:'12:00',end:'14:00',duration:30,gap:0,repeat:'weekly',until:'',exceptions:[],where:'Студия у м. Театральная',link:'',active:true},
    {id:'sat',date:'2026-10-24',start:'11:00',end:'12:30',duration:30,gap:0,repeat:'weekly',until:'',exceptions:[],where:'Онлайн, Яндекс Телемост',link:'',active:true}
  ],
  profiles: [
    {id:'egor@example.org',person:{firstName:'Егор',lastName:'Мельников',name:'Егор Мельников',email:'egor@example.org',phone:'+7 (900) 000-00-01',roles:['Ассистент педагога в мастерской'],channels:['Telegram'],telegram:'@egor_demo',participation:'Регулярно',slots:['Суббота·День']},progress:{done:Object.fromEntries(ONB.modules.map(m=>[m.id,true])),testDone:true,score:ONB.test.questions.length,best:ONB.test.questions.length,attempts:1}},
    {id:'mila@example.org',person:{firstName:'Мила',lastName:'Орлова',name:'Мила Орлова',email:'mila@example.org',phone:'+7 (900) 000-00-02',roles:['Предметная фотография'],channels:['Электронная почта'],participation:'По задачам'},progress:{done:Object.fromEntries(ONB.modules.slice(0,2).map(m=>[m.id,true])),best:null,attempts:0}}
  ],
  bookings:[{id:'demo-egor',candidateId:'egor@example.org',slotId:'fri@2026-10-23@12:00',windowId:'fri',date:'2026-10-23',start:'12:00',end:'12:30',gap:0,where:'Студия у м. Театральная',link:'',status:'booked',history:[{text:'Егор записался на встречу',when:'21 октября'}]}]
});
let interviewFallback;
function interviewRead(){
  try {const raw=localStorage.getItem(INTERVIEW_KEY);if(raw)return JSON.parse(raw);}catch(_){}
  if(!interviewFallback)interviewFallback=interviewDefaults();
  return JSON.parse(JSON.stringify(interviewFallback));
}
function interviewWrite(data){
  interviewFallback=JSON.parse(JSON.stringify(data));
  try{localStorage.setItem(INTERVIEW_KEY,JSON.stringify(data));}catch(_){}
  if(typeof window!=='undefined'&&typeof window.dispatchEvent==='function'&&typeof CustomEvent==='function')window.dispatchEvent(new CustomEvent('opora-interviews-change'));
}
function interviewImportLegacy(){
  let old;try{old=JSON.parse(localStorage.getItem('dm-proto-v1')||'null');}catch(_){return;}
  if(!old?.me)return;
  const id=interviewIdentity(old.me),data=interviewRead();if(!id||data.profiles.some(p=>p.id===id))return;
  const profile={id,person:old.me,progress:{done:old.done||{},best:old.test?.best??null,attempts:old.test?.attempts||0},legacyImported:true};
  if(old.meeting){
    const match=String(old.meeting.day||'').match(/(\d{1,2})\s+октябр/),start=old.meeting.time;
    if(match&&Number.isFinite(interviewMinutes(start))){const date='2026-10-'+match[1].padStart(2,'0');if(scheduleValid(date))data.bookings.push({id:'legacy-'+Date.now(),candidateId:id,slotId:'legacy-'+id,windowId:'import',date,start,end:interviewTime(interviewMinutes(start)+30),gap:0,where:old.meeting.where||'',link:'',status:'booked',history:[{text:'Запись перенесена из прежнего кабинета',when:'Ранее'}]});}
    else profile.request={text:'Проверьте прежнюю запись: '+(old.meeting.day||'')+', '+(start||''),status:'new'};
  }
  data.profiles.unshift(profile);interviewWrite(data);
}
function interviewSync(){
  const person=loadCandidate();if(!person)return;
  const id=interviewIdentity(person);if(!id)return;
  const data=interviewRead(),progress=loadProgress(),old=data.profiles.find(p=>p.id===id);
  const profile={...old,id,person,progress:{done:progress.done,testDone:progress.testDone,score:progress.score,best:progress.best,attempts:progress.attempts}};
  // Retain a previously chosen demo meeting when moving from the old candidate flow.
  if(progress.meeting&&!old?.legacyImported&&!data.bookings.some(b=>b.candidateId===id)){
    const match=String(progress.meeting.day||'').match(/(\d{1,2})\s+октябр/),start=progress.meeting.time;
    if(match&&Number.isFinite(interviewMinutes(start))){const date='2026-10-'+match[1].padStart(2,'0');if(scheduleValid(date))data.bookings.push({id:'import-'+Date.now(),candidateId:id,slotId:'import-'+id,windowId:'import',date,start,end:interviewTime(interviewMinutes(start)+30),gap:0,where:progress.meeting.where||'',link:'',status:'booked',history:[{text:'Перенесено из прежней записи',when:'Ранее'}]});}
    profile.legacyImported=true;
  }
  if(JSON.stringify(old)!==JSON.stringify(profile)){
    data.profiles=old?data.profiles.map(p=>p.id===id?profile:p):[profile,...data.profiles];interviewWrite(data);
  }
}
const interviewReady = profile => !!profile&&ONB.modules.every(m=>profile.progress.done?.[m.id])&&(profile.progress.testDone===true||profile.progress.best!=null);
const interviewCurrent = (data,id) => {const all=data.bookings.filter(b=>b.candidateId===id),active=all.find(b=>b.status==='booked'),last=all.slice(-1)[0];return active||(last?.status==='completed'?last:null);};
const interviewMatches = (w,date) => date>=w.date&&(!w.until||date<=w.until)&&!w.exceptions.includes(date)&&(w.repeat==='weekly'?scheduleDate(date).getUTCDay()===scheduleDate(w.date).getUTCDay():date===w.date);
function interviewSlots(data,from,to,excludeBooking='',includeClosed=false){
  const result=[];
  for(let date=from;date<=to;date=scheduleAdd(date,1))for(const w of data.windows){
    if((!w.active&&!includeClosed)||!interviewMatches(w,date))continue;
    for(let n=interviewMinutes(w.start);n+Number(w.duration)<=interviewMinutes(w.end);n+=Number(w.duration)+Number(w.gap)){
      const slot={id:w.id+'@'+date+'@'+interviewTime(n),windowId:w.id,date,start:interviewTime(n),end:interviewTime(n+Number(w.duration)),gap:Number(w.gap),where:w.where,link:w.link};
      const busy=data.bookings.find(b=>b.status==='booked'&&b.id!==excludeBooking&&b.date===date&&n<interviewMinutes(b.end)+Number(b.gap||0)&&interviewMinutes(b.start)<n+Number(w.duration)+Number(w.gap));
      result.push({...slot,busy:!!busy,booking:busy||null});
    }
  }
  return result.sort((a,b)=>(a.date+a.start).localeCompare(b.date+b.start));
}
function interviewBook(candidateId,slotId,bookingId='',actor='Кандидат'){
  const data=interviewRead(),profile=data.profiles.find(p=>p.id===candidateId);
  // Записаться можно параллельно со знакомством с фондом.
  if(!profile)return {error:'Сначала заполните анкету волонтёра.'};
  const old=bookingId?data.bookings.find(b=>b.id===bookingId&&b.candidateId===candidateId&&b.status==='booked'):null;
  if(bookingId&&!old)return {error:'Запись уже изменилась. Обновите список встреч.'};
  if(!bookingId&&data.bookings.some(b=>b.candidateId===candidateId&&b.status==='booked'))return {error:'У кандидата уже есть назначенная встреча.'};
  const date=slotId.split('@')[1];if(!scheduleValid(date)||!interviewFuture(date,slotId.split('@')[2]))return {error:'Выберите будущее время.'};
  const slot=interviewSlots(data,date,date,bookingId).find(s=>s.id===slotId&&!s.busy);
  if(!slot)return {error:'Это время уже занято или закрыто. Выберите другое.'};
  const entry={...old,...slot,id:old?.id||'meeting-'+Date.now()+'-'+Math.random().toString(36).slice(2,7),slotId:slot.id,candidateId,status:'booked',history:[...(old?.history||[]),{text:actor+(old?' перенёс встречу':' записал встречу')+' на '+interviewDay(date)+', '+slot.start,when:'Сейчас'}]};
  delete entry.busy;delete entry.booking;
  data.bookings=old?data.bookings.map(b=>b.id===old.id?entry:b):[...data.bookings,entry];interviewWrite(data);return {booking:entry};
}
function interviewCancel(id,reason,actor='Координатор'){
  if(!reason.trim())return {error:'Укажите причину отмены.'};
  const data=interviewRead(),b=data.bookings.find(b=>b.id===id&&b.status==='booked');if(!b)return {error:'Эта запись уже изменилась.'};
  data.bookings=data.bookings.map(x=>x.id===id?{...x,status:'cancelled',cancelReason:reason,history:[...x.history,{text:actor+' отменил встречу: '+reason,when:'Сейчас'}]}:x);
  interviewWrite(data);return {};
}
function interviewSaveWindow(draft){
  const data=interviewRead(),d={...draft,duration:Number(draft.duration),gap:Number(draft.gap),exceptions:[...(draft.exceptions||[])]};
  if(!scheduleValid(d.date)||!Number.isFinite(interviewMinutes(d.start))||!Number.isFinite(interviewMinutes(d.end))||interviewMinutes(d.end)<=interviewMinutes(d.start)||!d.where.trim()||![15,20,30,45,60].includes(d.duration)||!Number.isInteger(d.gap)||d.gap<0||d.gap>60||interviewMinutes(d.end)-interviewMinutes(d.start)<d.duration)return {error:'Проверьте дату, время, длительность и место. В окне должна помещаться хотя бы одна встреча.'};
  if(d.until&&(!scheduleValid(d.until)||d.until<d.date))return {error:'Дата окончания не может быть раньше первой даты.'};
  if(d.link&&!/^https?:\/\//i.test(d.link))return {error:'Ссылка должна начинаться с https:// или http://.'};
  for(const other of data.windows.filter(w=>w.id!==d.id&&w.active&&d.active)){
    const from=d.date>other.date?d.date:other.date,limit=[d.until,other.until].filter(Boolean).sort()[0];
    if(limit&&limit<from)continue;
    const to=limit&&limit<scheduleAdd(from,7)?limit:scheduleAdd(from,7);
    for(let date=from;date<=to;date=scheduleAdd(date,1))if(interviewMatches(d,date)&&interviewMatches(other,date)&&d.start<other.end&&other.start<d.end)return {error:'Это время пересекается с другим окном доступности.'};
  }
  const existing=data.windows.find(w=>w.id===d.id);const next={...data,windows:existing?data.windows.map(w=>w.id===d.id?d:w):[...data.windows,d]};
  for(const b of data.bookings.filter(b=>b.windowId===d.id&&b.status==='booked')){
    const same=interviewSlots({...next,bookings:[]},b.date,b.date,'',true).find(s=>s.id===b.slotId&&s.end===b.end&&s.gap===b.gap&&s.where===b.where&&s.link===b.link);
    if(!same)return {error:'В этом окне есть назначенные встречи. Сначала перенесите или отмените их.'};
  }
  interviewWrite(next);return {};
}
function interviewFinish(id,result,publicNote,privateNote,nextDate){
  if(!result||!publicNote.trim())return {error:'Выберите следующий шаг и запишите договорённость для волонтёра.'};
  if(nextDate&&!scheduleValid(nextDate))return {error:'Проверьте дату следующего контакта.'};
  const data=interviewRead(),old=data.bookings.find(b=>b.id===id&&b.status==='booked');if(!old)return {error:'Эта запись уже изменилась.'};
  data.bookings=data.bookings.map(b=>b.id===id?{...b,status:result==='Не пришёл'?'missed':'completed',result,publicNote,privateNote,nextDate,history:[...b.history,{text:'Итог встречи: '+result,when:'Сейчас'}]}:b);interviewWrite(data);return {};
}
function interviewSubscribe(component){
  if(typeof window==='undefined'||!window.addEventListener)return ()=>{};
  const refresh=()=>{if(typeof component.interviewRefresh==='function')component.interviewRefresh();else component.setState({interviewRevision:Date.now()});};
  const storage=e=>{if(e.key===INTERVIEW_KEY)refresh();};
  window.addEventListener('storage',storage);window.addEventListener('focus',refresh);window.addEventListener('opora-interviews-change',refresh);
  return ()=>{window.removeEventListener('storage',storage);window.removeEventListener('focus',refresh);window.removeEventListener('opora-interviews-change',refresh);};
}
