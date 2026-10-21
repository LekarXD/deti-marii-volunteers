const BLOCK_FLAGS = ['isLead','isFacts','isTimeline','isIcards','isStory','isRules','isPhrases','isQuiz','isVideo','isCallout'];
const CARD_TINTS = ['a-ic-o','a-ic-b','a-ic-g','a-ic-v','a-ic-y'];
class Component extends DCLogic {
 constructor(p){super(p);this.state={me:ensureCandidate(),pr:loadProgress(),view:null,read:{},quiz:{},run:null};this.onScroll=this.onScroll.bind(this);}
 componentDidMount(){window.addEventListener('scroll',this.onScroll,{passive:true});window.addEventListener('resize',this.onScroll);this.after();}
 componentDidUpdate(){this.after();}
 componentWillUnmount(){window.removeEventListener('scroll',this.onScroll);window.removeEventListener('resize',this.onScroll);if(this.io)this.io.disconnect();}
 after(){this.reveal();this.onScroll();}
 // Блоки появляются при прокрутке, числа «набегают». Всё, что уже выше края экрана, показываем сразу —
 // даже если пролистали очень быстро.
 showEl(el){if(el.classList.contains('is-in'))return;el.classList.add('is-in');if(this.io)this.io.unobserve(el);const c=el.querySelector('.a-count');if(!c||c.dataset.done)return;c.dataset.done='1';const to=+c.dataset.to,suf=c.dataset.suffix||'';if(this.reduce||!to)return;const t0=performance.now(),dur=1200;const f=t=>{const k=Math.min(1,(t-t0)/dur);c.textContent=Math.round(to*(1-Math.pow(1-k,3)))+suf;if(k<1)requestAnimationFrame(f);};c.textContent='0'+suf;requestAnimationFrame(f);}
 // Анимация появления — только на первом шаге (история фонда); дальше блоки видны сразу, без «всплываний»
 reveal(){const cur=this.current();this.reduce=!!(window.matchMedia&&matchMedia('(prefers-reduced-motion: reduce)').matches)||cur.test||cur.i>0;document.body.classList.toggle('a-static',this.reduce);
  if(!this.io)this.io=new IntersectionObserver(es=>es.forEach(e=>{if(e.isIntersecting)this.showEl(e.target);}),{threshold:.15,rootMargin:'0px 0px -40px 0px'});
  document.querySelectorAll('.a-reveal:not(.is-in)').forEach(el=>{if(this.reduce)el.classList.add('is-in');else this.io.observe(el);});this.catchUp();}
 catchUp(){document.querySelectorAll('.a-reveal:not(.is-in)').forEach(el=>{if(el.getBoundingClientRect().top<window.innerHeight*.92)this.showEl(el);});}
 // Как с пользовательским соглашением: «дальше» открывается, когда шаг долистан до конца
 onScroll(){this.catchUp();const bar=document.getElementById('a-readbar');if(bar){const h=document.documentElement,max=h.scrollHeight-h.clientHeight;bar.style.width=(max>0?Math.min(100,100*h.scrollTop/max):100)+'%';}
  const id=this.current().id,end=document.getElementById('a-read-end');if(!end||!id||this.state.read[id]||this.state.pr.done[id])return;if(end.getBoundingClientRect().top<=window.innerHeight)this.setState({read:{...this.state.read,[id]:true}});}
 // Без оглавления: открываем первый непройденный шаг, потом тест
 current(){const s=this.state,mods=ONB.modules;if(s.view==='test')return{test:true};if(s.view!=null)return{id:s.view,i:mods.findIndex(m=>m.id===s.view)};const i=mods.findIndex(m=>!s.pr.done[m.id]);return i<0?{test:true}:{id:mods[i].id,i};}
 save(pr){demoWrite('onboarding',pr);this.setState({pr});}
 open(view){this.setState({view});window.scrollTo(0,0);}
 blockView(b,mi,bi){const v={};BLOCK_FLAGS.forEach(k=>v[k]=false);v['is'+b.type[0].toUpperCase()+b.type.slice(1)]=true;
  v.text=b.text||'';v.title=b.title||'';v.hasTitle=!!b.title;v.intro=b.intro||'';v.duration=b.duration||'';v.cls=(b.tone==='warn'?'error':'hint')+' a-reveal';
  const it=b.items||[];
  if(b.type==='facts')v.items=it.map(([n,l])=>({n,l,to:parseInt(n,10)||0,suffix:String(n).replace(/^\d+/,'')}));
  else if(b.type==='timeline')v.items=it.map(([y,t,d])=>({y,t,d}));
  else if(b.type==='icards')v.items=it.map(x=>({...x,...icoFlags(x.icon),cls:'a-icard a-reveal '+CARD_TINTS[(bi||0)%CARD_TINTS.length]}));
  else if(b.type==='story')v.items=it.map(([t,d,icon],k)=>({t,d,...icoFlags(icon),cls:'a-stage a-reveal '+['a-ic-b','a-ic-y','a-ic-g'][k%3]}));
  else if(b.type==='rules')v.items=it.map((t,k)=>({t,n:k+1}));
  else if(b.type==='phrases')v.items=it.map(([say,avoid])=>({say,avoid}));
  else if(b.type==='quiz')v.items=it.map((x,k)=>{const key=mi+'-'+k,ans=this.state.quiz[key],answered=ans!=null,ok=ans===x.a;
   return {q:x.q,e:x.e,answered,fbCls:'a-fb '+(ok?'is-ok':'is-bad'),fbHead:ok?'Верно':'Не совсем',
    opts:x.o.map((o,j)=>({text:o,locked:answered,cls:'a-qopt'+(answered&&j===x.a?' is-right':'')+(answered&&j===ans&&!ok?' is-wrong':''),pick:()=>this.setState({quiz:{...this.state.quiz,[key]:j}})}))};});
  else v.items=[];
  return v;}
 renderVals(){const s=this.state,pr=s.pr,mods=ONB.modules,T=ONB.test,N=T.questions.length,cur=this.current(),total=mods.length+1;
  const m=cur.test?null:mods[cur.i],stepN=cur.test?total:cur.i+1,unlocked=!!m&&(pr.done[m.id]||s.read[m.id]),nxt=m?mods[cur.i+1]:null;
  const run=s.run,inQ=!!run&&run.i<N,showRes=cur.test&&(pr.testDone||(!!run&&run.i>=N)),q=inQ?T.questions[run.i]:null,ans=inQ?run.answers[run.i]:null,answered=ans!=null,ok=answered&&ans===q.a;
  const score=pr.testDone?pr.score:(run?run.answers.filter((a,k)=>a===T.questions[k].a).length:0);
  return {stepLabel:'Знакомство с фондом · шаг '+stepN+' из '+total,
   segs:Array.from({length:total},(_,k)=>({cls:k<stepN-1?'is-done':(k===stepN-1?'is-on':'')})),
   isModule:!!m,isTest:!!cur.test,modTitle:m?m.title:'',blocks:m?m.blocks.map((b,bi)=>this.blockView(b,cur.i,m.blocks.slice(0,bi).filter(x=>x.type==='icards').length+cur.i)):[],
   hasPrev:!!m&&cur.i>0,prev:()=>this.open(mods[cur.i-1].id),
   doneLocked:!!m&&!unlocked,doneCls:'btn btn-lg '+(unlocked?'btn-primary a-unlocked':'btn-subtle'),doneLabel:!m?'':(unlocked?(nxt?'Понятно, дальше':'Понятно, к тесту'):'Дочитайте до конца ↓'),
   done:()=>{if(!m)return;this.save({...pr,done:{...pr.done,[m.id]:true}});this.open(nxt?nxt.id:'test');},
   testTitle:T.title,testText:T.intro,testIntro:!!cur.test&&!run&&!pr.testDone,start:()=>this.setState({run:{i:0,answers:[]}}),
   testQuestion:!!cur.test&&inQ,qNum:inQ?run.i+1:0,qTotal:N,qText:q?q.q:'',
   qOpts:q?q.o.map((o,j)=>({text:o,locked:answered,cls:'a-answer'+(answered&&j===q.a?' is-right':'')+(answered&&j===ans&&!ok?' is-wrong':''),pick:()=>{const answers=[...run.answers];answers[run.i]=j;this.setState({run:{...run,answers}});}})):[],
   answered,sheetCls:'a-sheet-card '+(ok?'is-ok':'is-bad'),sheetMark:ok?'✓':'✕',explHead:ok?'Верно!':'Не совсем',expl:q?q.e:'',
   nextQLabel:inQ&&run.i+1<N?'Следующий вопрос':'Завершить',
   nextQ:()=>{const r={...run,i:run.i+1};if(r.i>=N){const sc=r.answers.filter((a,k)=>a===T.questions[k].a).length;this.save({...pr,testDone:true,score:sc});}this.setState({run:r});window.scrollTo(0,0);},
   resultNext:(()=>{const mt=interviewCurrent(interviewRead(),interviewIdentity(loadCandidate()));return mt?.status==='booked'?'Ждём вас на встрече с координатором: '+interviewDay(mt.date)+', '+mt.start+'.':'Дальше — встреча с координатором. Выбрать время можно в личном кабинете.';})(),
   testResult:showRes,scoreLine:'Правильных ответов: '+score+' из '+N};}
}
