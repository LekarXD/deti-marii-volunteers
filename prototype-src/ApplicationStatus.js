class Component extends DCLogic {
 constructor(p){super(p);this.state={me:loadCandidate(),pr:loadProgress(),picked:null};}
 save(pr){demoWrite('onboarding',pr);this.setState({pr});}
 renderVals(){const s=this.state,me=s.me,pr=s.pr,M=ONB.meeting,total=ONB.modules.length,n=ONB.modules.filter(m=>pr.done[m.id]).length,N=ONB.test.questions.length,passed=pr.best!=null&&pr.best>=ONB.test.pass,allDone=n===total;
  const stages=[
   {title:'Заявка',sub:'отправлена',done:!!me},
   {title:'Знакомство с фондом',sub:n+' из '+total+' шагов',done:allDone},
   {title:'Тест',sub:pr.best==null?'после знакомства':pr.best+' из '+N+(passed?' — пройден':''),done:passed},
   {title:'Встреча с координатором',sub:pr.meeting?pr.meeting.day+', '+pr.meeting.time:'после теста',done:!!pr.meeting},
   {title:'Первое занятие',sub:'подберём на встрече',done:false}];
  const now=stages.findIndex(x=>!x.done);
  const fmt=v=>Array.isArray(v)?v.join(', ').replace(/·/g,' '):(v||'');
  const answers=me?[['Роли',fmt(me.roles)],['Как помогать',fmt(me.participation)],['Где удобно',fmt(me.places)],['Когда удобно',fmt(me.slots)],['Связь',fmt(me.channels)+(me.telegram?' · '+me.telegram:'')],['Телефон и почта',fmt(me.phone)+' · '+fmt(me.email)]].filter(x=>x[1]).map(([k,v])=>({k,v})):[];
  const nextStep=!allDone?{e:n?'Продолжите':'Следующий шаг',t:'Знакомство с фондом',l:'Шесть коротких шагов: кто мы, кому помогаем, как себя вести и как общаться с участниками. Около 25 минут.',b:n?'Продолжить':'Начать',h:'Onboarding.dc.html'}:(!passed?{e:'Осталось немного',t:ONB.test.title,l:'Чтобы записаться на встречу, ответьте правильно на '+ONB.test.pass+' вопросов из '+N+'.',b:'Пройти тест',h:'Onboarding.dc.html?view=test'}:null);
  return {noCandidate:!me,hasCandidate:!!me,first:firstName(me),
   stages:stages.map((x,i)=>({...x,cls:x.done?'is-done':(i===now?'is-now':''),mark:x.done?'✓':String(i+1)})),
   showNext:!!nextStep,nextEyebrow:nextStep?nextStep.e:'',nextTitle:nextStep?nextStep.t:'',nextLead:nextStep?nextStep.l:'',nextButton:nextStep?nextStep.b:'',nextHref:nextStep?nextStep.h:'#',
   showPicker:passed&&!pr.meeting,booked:!!pr.meeting,meetTitle:M.title,meetText:M.text,coordinator:M.coordinator,
   slots:M.slots.map((sl,i)=>({...sl,cls:s.picked===i?'opt is-on':'opt',checked:s.picked===i,pick:()=>this.setState({picked:i})})),
   cantBook:s.picked==null,book:()=>{this.save({...pr,meeting:M.slots[s.picked]});this.setState({picked:null});},
   meetWhen:pr.meeting?pr.meeting.day+', '+pr.meeting.time:'',meetWhere:pr.meeting?pr.meeting.where:'',unbook:()=>this.save({...pr,meeting:null}),
   answers,
   fillDemo:()=>{demoWrite('candidate',DEMO_CANDIDATE);this.setState({me:DEMO_CANDIDATE});},
   passAll:()=>{const me2=s.me||DEMO_CANDIDATE;demoWrite('candidate',me2);const done={};ONB.modules.forEach(m=>done[m.id]=true);this.setState({me:me2});this.save({...pr,done,best:N,attempts:1});},
   reset:()=>{demoWrite('candidate',null);demoWrite('onboarding',freshProgress());this.setState({me:null,pr:freshProgress(),picked:null});}};}
}
