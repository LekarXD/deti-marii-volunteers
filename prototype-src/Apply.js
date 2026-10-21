class Component extends DCLogic {
 constructor(p){super(p);const d=demoRead('apply-draft',{step:0,data:{}});this.state={step:Math.min(d.step||0,FORM.steps.length-1),data:d.data||{},errs:{},ui:{}};}
 persist(next){demoWrite('apply-draft',{step:next.step,data:next.data});}
 update(id,value){const data={...this.state.data,[id]:value};const errs={...this.state.errs};delete errs[id];this.setState({data,errs});this.persist({step:this.state.step,data});}
 go(step){this.setState({step,errs:{}});this.persist({step,data:this.state.data});window.scrollTo(0,0);}
 next(){const s=this.state,step=FORM.steps[s.step],data={...s.data};const errs=validateFields(step.fields,data);if(Object.keys(errs).length){this.setState({errs,data});return;}
  if(s.step<FORM.steps.length-1){this.setState({data});this.go(s.step+1);return;}
  // Отправка: сразу в личный кабинет на платформе, ссылка дублируется по SMS и на почту
  const me={...data,name:[data.firstName,data.lastName].filter(Boolean).join(' '),submittedAt:new Date().toISOString()};
  demoWrite('candidate',me);demoWrite('onboarding',freshProgress());demoWrite('apply-draft',{step:0,data:{}});location.href='ApplicationStatus.dc.html?welcome=1';}
 renderVals(){const s=this.state,step=FORM.steps[s.step],last=s.step===FORM.steps.length-1;
  return {eyebrow:'Стать волонтёром',title:FORM.title,intro:FORM.intro,
   steps:FORM.steps.map((x,i)=>({label:(i+1)+'. '+x.title,cls:i===s.step?'chip is-on':(i<s.step?'chip a-done':'chip')})),
   progressLabel:'Шаг '+(s.step+1)+' из '+FORM.steps.length,barStyle:'width:'+Math.round(100*(s.step+1)/FORM.steps.length)+'%',
   fields:fieldViews(step.fields,s.data,s.errs,(id,v)=>this.update(id,v),s.ui,k=>this.setState({ui:{...this.state.ui,[k]:!this.state.ui[k]}})),
   canBack:s.step>0,back:()=>this.go(s.step-1),next:()=>this.next(),nextLabel:last?'Отправить заявку':'Далее',hasErrors:Object.keys(s.errs).length>0,
   fillDemo:()=>{const data={...DEMO_CANDIDATE};this.setState({data,step:FORM.steps.length-1,errs:{}});this.persist({step:FORM.steps.length-1,data});},
   clear:()=>{this.setState({data:{},step:0,errs:{}});this.persist({step:0,data:{}});}};}
}
