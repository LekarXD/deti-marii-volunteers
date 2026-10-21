class Component extends DCLogic {
 constructor(p){super(p);interviewImportLegacy();const me=ensureCandidate();interviewSync();this.state={me,pr:loadProgress(),picking:false,picked:'',focus:INTERVIEW_TODAY,rescheduling:false,cancelling:false,cancelReason:'',requesting:false,requestText:'',error:'',notice:''};}
 componentDidMount(){this.unsubscribe=interviewSubscribe(this);}
 componentWillUnmount(){this.unsubscribe?.();}
 interviewRefresh(){const m=interviewCurrent(interviewRead(),interviewIdentity(this.state.me));if(this.state.rescheduling&&(!m||m.status!=='booked'||m.slotId!==this.state.movingSlot))this.setState({rescheduling:false,picked:'',notice:'Запись обновлена координатором',interviewRevision:Date.now()});else this.setState({interviewRevision:Date.now()});}
 save(pr){demoWrite('onboarding',pr);this.setState({pr});}
 openPicker(extra){this.setState({picking:true,picked:'',error:'',...extra});setTimeout(()=>document.getElementById('a-picker')?.scrollIntoView({behavior:'smooth',block:'start'}),50);}
 book(){const s=this.state,id=interviewIdentity(s.me),current=interviewCurrent(interviewRead(),id);const result=interviewBook(id,s.picked,s.rescheduling&&current?.status==='booked'?current.id:'','Волонтёр');this.setState(result.error?{error:result.error,picked:''}:{picked:'',picking:false,rescheduling:false,error:'',notice:s.rescheduling?'Встреча перенесена':'Вы записаны на встречу'});}
 // Прототип: сбросить записи кандидата и при необходимости записать на ближайшее свободное время
 demo(pr,withMeeting){const id=interviewIdentity(this.state.me),data=interviewRead();data.bookings=data.bookings.filter(b=>b.candidateId!==id);data.profiles=data.profiles.map(p=>p.id===id?{...p,request:null}:p);interviewWrite(data);this.save(pr);
  if(withMeeting){const slot=interviewSlots(interviewRead(),INTERVIEW_TODAY,scheduleAdd(INTERVIEW_TODAY,13)).find(sl=>!sl.busy&&interviewFuture(sl.date,sl.start));if(slot)interviewBook(id,slot.id,'','Волонтёр');}
  this.setState({picking:false,rescheduling:false,cancelling:false,requesting:false,picked:'',error:'',notice:''});}
 renderVals(){const s=this.state,me=s.me,pr=s.pr,data=interviewRead(),id=interviewIdentity(me),meeting=interviewCurrent(data,id),active=meeting?.status==='booked',completed=meeting?.status==='completed';
  const total=ONB.modules.length,n=ONB.modules.filter(m=>pr.done[m.id]).length,onboarded=!!pr.testDone;
  const allDone={};ONB.modules.forEach(m=>allDone[m.id]=true);
  const meetWhen=meeting?interviewDay(meeting.date)+', '+meeting.start:'';
  // Записался, но не знакомился с фондом — после подключения уведомлений подталкиваем к знакомству
  const showNudge=active&&!onboarded&&!!pr.tg;
  const showPicker=!completed&&((!meeting&&s.picking)||(active&&s.rescheduling));
  const from=scheduleMonday(s.focus),to=scheduleAdd(from,6),available=interviewSlots(data,from,to,s.rescheduling&&active?meeting.id:'').filter(sl=>!sl.busy&&interviewFuture(sl.date,sl.start)&&sl.id!==meeting?.slotId);
  const last=data.bookings.filter(b=>b.candidateId===id).slice(-1)[0];
  return {first:firstName(me),
   showReview:!completed,reviewTitle:FORM.done.title,reviewText:FORM.done.text,
   showNudge,meetWhen,onboarded,
   onbCardCls:'card a-two-card'+(onboarded?' is-done':'')+(showNudge?' is-nudge':''),
   onbText:onboarded?'Вы прошли знакомство с фондом. Вернуться к материалам можно в любой момент.':(n?'Пройдено '+n+' из '+total+' шагов. Осталось немного — и небольшой тест.':'Около 20 минут: история фонда, кому мы помогаем, кодекс этики и как общаться с участниками.'),
   onbButton:onboarded?'Посмотреть ещё раз':(n?'Продолжить':'Начать'),onbBtnCls:'btn btn-lg '+(onboarded?'btn-ghost':'btn-dark'),
   meetCardCls:'card a-two-card'+(meeting?' is-done':''),coordinator:ONB.meeting.coordinator,meetText:ONB.meeting.text,
   notBooked:!meeting,canOpenPicker:!meeting&&!s.picking,openPicker:()=>this.openPicker({}),
   hasCancellation:!meeting&&last?.status==='cancelled',cancellationText:last?.cancelReason||'',
   booked:!!active,completed:!!completed,meetWhere:meeting?.where||'',hasMeetingLink:!!meeting?.link,meetingLink:meeting?.link||'#',publicNote:meeting?.publicNote||'',result:meeting?.result||'',nextContact:meeting?.nextDate?interviewDay(meeting.nextDate):'',hasNextContact:!!meeting?.nextDate,
   road:!!pr.road,toggleRoad:()=>this.save({...pr,road:!pr.road}),
   reschedule:()=>this.openPicker({rescheduling:true,movingSlot:meeting?.slotId,focus:meeting?.date||s.focus}),
   askCancel:()=>this.setState({cancelling:true,cancelReason:'',error:''}),cancelling:s.cancelling,cancelReason:s.cancelReason,changeCancelReason:e=>this.setState({cancelReason:e.target.value,error:''}),keepMeeting:()=>this.setState({cancelling:false,error:''}),
   cancelMeeting:()=>{const r=interviewCancel(meeting?.id,s.cancelReason,'Волонтёр');this.setState(r.error?{error:r.error}:{cancelling:false,rescheduling:false,picked:'',notice:'Запись отменена. Можно выбрать другое время.',error:''});},
   showPicker,rescheduling:!!active&&s.rescheduling,pickerTitle:s.rescheduling?'Выберите другое время':'Выберите время встречи',
   closePicker:()=>this.setState({picking:false,rescheduling:false,picked:'',error:''}),closeLabel:s.rescheduling?'Оставить прежнее время':'Свернуть',
   focus:s.focus,changeFocus:e=>{if(scheduleValid(e.target.value))this.setState({focus:e.target.value,picked:'',error:''});},periodLabel:interviewDay(from)+' — '+scheduleLabel(to,{day:'numeric',month:'long'}),previous:()=>this.setState({focus:scheduleAdd(s.focus,-7),picked:''}),next:()=>this.setState({focus:scheduleAdd(s.focus,7),picked:''}),today:()=>this.setState({focus:INTERVIEW_TODAY,picked:''}),
   slotDays:[...new Set(available.map(sl=>sl.date))].map(date=>({dateLabel:interviewDay(date),slots:available.filter(sl=>sl.date===date).map(sl=>({...sl,label:sl.start+'–'+sl.end,cls:'i-slot'+(s.picked===sl.id?' is-on':''),checked:s.picked===sl.id?'true':'false',pick:()=>this.setState({picked:sl.id,error:''})}))})),emptySlots:!available.length,cantBook:!available.some(sl=>sl.id===s.picked),book:()=>this.book(),bookLabel:s.rescheduling?'Подтвердить перенос':'Записаться',
   requesting:s.requesting,requestText:s.requestText,startRequest:()=>this.setState({requesting:true,error:''}),changeRequest:e=>this.setState({requestText:e.target.value,error:''}),cancelRequest:()=>this.setState({requesting:false,error:''}),
   sendRequest:()=>{if(!s.requestText.trim()){this.setState({error:'Напишите, когда вам удобно встретиться.'});return;}const fresh=interviewRead();fresh.profiles=fresh.profiles.map(p=>p.id===id?{...p,request:{text:s.requestText,status:'new'}}:p);interviewWrite(fresh);this.setState({requesting:false,picking:false,requestText:'',notice:'Ваш запрос появился у координатора',error:''});},
   tgOn:!!pr.tg,tgOff:!pr.tg,
   tgText:pr.tg?'Бот напомнит о встрече накануне и подскажет следующий шаг.':'Подключите бота фонда — он напомнит о встрече и подскажет следующий шаг.',
   connectTg:()=>this.save({...pr,tg:true}),
   notice:s.notice,dismissNotice:()=>this.setState({notice:''}),dismissError:()=>this.setState({error:''}),error:s.error,hasError:!!s.error,
   demoFresh:()=>this.demo(freshProgress(),false),
   demoBookedOnly:()=>this.demo({...freshProgress(),tg:true},true),
   demoAll:()=>this.demo({...freshProgress(),done:allDone,testDone:true,score:9,tg:true},true)};}
}
