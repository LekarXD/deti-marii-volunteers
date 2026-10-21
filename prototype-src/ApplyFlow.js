class Component extends DCLogic {
 constructor(p){super(p);const d=demoRead('flow-draft',{i:0,data:{}});this.state={i:d.i||0,data:d.data||{},errs:{},ui:{}};}
 persist(i,data){demoWrite('flow-draft',{i,data});}
 // Экраны, где все поля скрыты условиями, пропускаем
 screens(data){return FORM.flow.filter(sc=>sc.fields.some(id=>visibleFor(fieldById(id),data)));}
 fields(sc){return sc.fields.map((id,k)=>{const f=fieldById(id);return k===0&&!sc.keepLabels?{...f,hideLabel:true,why:''}:f;});}
 update(id,value){const data={...this.state.data,[id]:value},errs={...this.state.errs};delete errs[id];this.setState({data,errs});this.persist(this.state.i,data);
  const sc=this.screens(data)[this.state.i];
  // Один вариант ответа — сразу к следующему вопросу
  if(sc&&sc.auto&&sc.fields[0]===id)setTimeout(()=>this.next(),320);}
 go(i){this.setState({i,errs:{}});this.persist(i,this.state.data);window.scrollTo(0,0);this.focusFirst();}
 // Курсор сразу в первом поле — можно печатать и жать Enter
 focusFirst(){setTimeout(()=>{const el=document.querySelector('.f-form input:not([type=checkbox]),.f-form textarea');if(el)el.focus({preventScroll:true});},60);}
 componentDidMount(){this.focusFirst();}
 next(){const s=this.state,list=this.screens(s.data),sc=list[s.i],data={...s.data};if(!sc)return;const errs=validateFields(this.fields(sc),data);if(Object.keys(errs).length){this.setState({errs,data});return;}
  if(s.i<list.length-1){this.setState({data});this.go(s.i+1);return;}
  demoWrite('flow-draft',{i:0,data:{}});submitCandidate(data);}
 renderVals(){const s=this.state,list=this.screens(s.data),i=Math.min(s.i,list.length-1),sc=list[i],last=i===list.length-1;
  const fs=this.fields(sc),textarea=fs.some(f=>f.type==='textarea'&&visibleFor(f,s.data));
  return {counter:'Вопрос '+(i+1)+' из '+list.length,barStyle:'width:'+Math.round(100*(i+1)/list.length)+'%',
   chapter:sc.chapter,qTitle:sc.title,qHint:sc.hint||'',hasHint:!!sc.hint,qCls:'f-q '+(i%2?'f-q-a':'f-q-b'),
   fields:fieldViews(fs,s.data,s.errs,(id,v)=>this.update(id,v),s.ui,k=>this.setState({ui:{...this.state.ui,[k]:!this.state.ui[k]}})),
   canBack:i>0,back:()=>this.go(i-1),next:()=>this.next(),nextLabel:last?'Отправить анкету':'Дальше',showEnter:!textarea&&!last,hasErrors:Object.keys(s.errs).length>0,
   key:e=>{if(e.key==='Enter'&&e.target.tagName!=='TEXTAREA'&&e.target.tagName!=='BUTTON'){e.preventDefault();this.next();}},
   fillDemo:()=>{const data={...DEMO_CANDIDATE},n=this.screens(data).length-1;this.setState({data,i:n,errs:{}});this.persist(n,data);},
   clear:()=>{this.setState({data:{},i:0,errs:{}});this.persist(0,{});}};}
}
