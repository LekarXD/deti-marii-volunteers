class Component extends DCLogic {
 constructor(p){super(p);const more=typeof MORE_MODE!=='undefined';const me=more?ensureCandidate():null;
  this.state={more,data:more?{...me}:demoRead('quick-draft',{}),errs:{},ui:{}};}
 // Вопросы «потом» — все поля анкеты, кроме уже заданных; заголовки блоков без полей убираем
 fieldList(){const Q=FORM.quick.fields.map(quickField);if(!this.state.more)return Q;const asked=new Set(Q.map(f=>f.id));
  const rest=FORM.steps.flatMap(s=>s.fields).filter(f=>f.type==='section'||!asked.has(f.id));
  return rest.filter((f,k)=>f.type!=='section'||(rest[k+1]&&rest[k+1].type!=='section')).map(f=>f.id==='s-dir'?{...f,title:'Что вы умеете',note:''}:f);}
 update(id,value){const data={...this.state.data,[id]:value},errs={...this.state.errs};delete errs[id];this.setState({data,errs});if(!this.state.more)demoWrite('quick-draft',data);}
 submit(){const s=this.state,data={...s.data},errs=validateFields(this.fieldList(),data);if(Object.keys(errs).length){this.setState({errs,data});window.scrollTo(0,0);return;}
  if(s.more){demoWrite('candidate',{...data,moreDone:true});location.href='ApplicationStatus.dc.html';return;}
  demoWrite('quick-draft',{});submitCandidate(data,{quick:true});}
 renderVals(){const s=this.state,Q=FORM.quick;
  return {isQuick:!s.more,isMore:s.more,title:s.more?Q.moreTitle:Q.title,intro:s.more?Q.moreIntro:Q.intro,
   path:FORM.path.map((x,i)=>({...x,...icoFlags(x.icon),cls:i===0?'is-now':'',meta:i===0?'1 минута':x.meta})),
   fields:fieldViews(this.fieldList(),s.data,s.errs,(id,v)=>this.update(id,v),s.ui,k=>this.setState({ui:{...this.state.ui,[k]:!this.state.ui[k]}})),
   submit:()=>this.submit(),hasErrors:Object.keys(s.errs).length>0,
   fillDemo:()=>{const data={...DEMO_CANDIDATE};this.setState({data,errs:{}});if(!s.more)demoWrite('quick-draft',data);},
   clear:()=>{const data=s.more?{firstName:s.data.firstName,lastName:s.data.lastName,phone:s.data.phone,email:s.data.email,birthdate:s.data.birthdate,consentPD:true,quick:true}:{};this.setState({data,errs:{}});if(!s.more)demoWrite('quick-draft',{});}};}
}
