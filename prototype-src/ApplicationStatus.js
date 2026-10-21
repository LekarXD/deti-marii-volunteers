class Component extends DCLogic {
 constructor(p){super(p);this.state={me:ensureCandidate(),pr:loadProgress(),picked:null,welcome:new URLSearchParams(location.search).has('welcome')};}
 save(pr){demoWrite('onboarding',pr);this.setState({pr});}
 renderVals(){const s=this.state,me=s.me,pr=s.pr,M=ONB.meeting,total=ONB.modules.length,n=ONB.modules.filter(m=>pr.done[m.id]).length,onboarded=!!pr.testDone;
  const stages=[
   {title:'Заявка',sub:'отправлена',done:true},
   {title:'Знакомство с фондом',sub:onboarded?'пройдено':(n?n+' из '+total+' шагов':'около 20 минут'),done:onboarded},
   {title:'Встреча с координатором',sub:pr.meeting?pr.meeting.day+', '+pr.meeting.time:'после знакомства',done:!!pr.meeting},
   {title:'Первый выход',sub:'обсудим на встрече',done:false}];
  const now=stages.findIndex(x=>!x.done);
  const allDone={};ONB.modules.forEach(m=>allDone[m.id]=true);
  return {welcome:s.welcome,welcomeTitle:FORM.done.title,welcomeText:FORM.done.text,first:firstName(me),
   stages:stages.map((x,i)=>({...x,cls:x.done?'is-done':(i===now?'is-now':''),mark:x.done?'✓':String(i+1)})),
   showOnboarding:!onboarded,onbEyebrow:n?'Продолжите':'Следующий шаг',onbButton:n?'Продолжить':'Начать',
   onbLead:'Четыре коротких шага о фонде, участниках и правилах общения и небольшой тест. После него выберете время встречи с координатором.',
   showPicker:onboarded&&!pr.meeting,booked:!!pr.meeting,meetTitle:M.title,meetText:M.text,coordinator:M.coordinator,
   slots:M.slots.map((sl,i)=>({...sl,cls:s.picked===i?'opt is-on':'opt',checked:s.picked===i,pick:()=>this.setState({picked:i})})),
   road:!!pr.road,toggleRoad:()=>this.save({...pr,road:!pr.road}),
   cantBook:s.picked==null,book:()=>{this.save({...pr,meeting:M.slots[s.picked]});this.setState({picked:null,welcome:false});window.scrollTo(0,0);},
   meetWhen:pr.meeting?pr.meeting.day+', '+pr.meeting.time:'',meetWhere:pr.meeting?pr.meeting.where:'',unbook:()=>this.save({...pr,meeting:null}),
   demoFresh:()=>{this.save(freshProgress());this.setState({welcome:true,picked:null});},
   demoOnboarded:()=>{this.save({...freshProgress(),done:allDone,testDone:true,score:9});this.setState({welcome:false,picked:null});},
   demoBooked:()=>{this.save({...freshProgress(),done:allDone,testDone:true,score:9,meeting:M.slots[1]});this.setState({welcome:false,picked:null});}};}
}
