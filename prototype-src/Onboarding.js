const BLOCK_FLAGS = ['isLead','isText','isFacts','isTimeline','isCards','isList','isSteps','isPhrases','isSituations','isPillars','isCheck','isVideo','isCallout','isMore'];
const PILLAR_COLORS = ['a-pillar a-p-o','a-pillar a-p-b','a-pillar a-p-g','a-pillar a-p-v'];
function blockView(b){
 const v={};BLOCK_FLAGS.forEach(k=>v[k]=false);
 const key='is'+b.type[0].toUpperCase()+b.type.slice(1);v[key]=true;
 v.text=b.text||'';v.title=b.title||'';v.hasTitle=!!b.title;v.intro=b.intro||'';v.duration=b.duration||'';
 v.ordered=!!b.ordered;v.bullets=!b.ordered;v.cls=b.tone==='warn'?'error':'hint';
 v.paras=String(b.text||'').split(/\n\s*\n/);
 const it=b.items||[];
 if(b.type==='facts')v.items=it.map(([n,l])=>({n,l}));
 else if(b.type==='timeline')v.items=it.map(([y,t,d])=>({y,t,d}));
 else if(b.type==='cards')v.items=it.map(([t,d])=>({t,d}));
 else if(b.type==='list')v.items=it.map((t,i)=>({t,n:i+1}));
 else if(b.type==='steps')v.items=it.map(([t,d],i)=>({t,d,n:i+1}));
 else if(b.type==='phrases'){v.title=b.title||'Как говорить';v.items=it.map(([say,avoid,why])=>({say,avoid,why:why||'',hasWhy:!!why}));}
 else if(b.type==='situations')v.items=it.map(x=>({title:x.title,do:x.do,dont:x.dont}));
 else if(b.type==='pillars')v.items=it.map((x,i)=>({...x,cls:PILLAR_COLORS[i%4]}));
 else if(b.type==='check')v.items=it;
 else v.items=[];
 v.blocks=b.type==='more'?b.blocks.map(blockView):[];
 return v;
}
class Component extends DCLogic {
 constructor(p){super(p);const q=new URLSearchParams(location.search);this.state={me:loadCandidate(),pr:loadProgress(),view:q.get('view')==='test'?'test':'hub',read:{},run:null,ui:{}};this.onScroll=this.onScroll.bind(this);}
 componentDidMount(){window.addEventListener('scroll',this.onScroll,{passive:true});window.addEventListener('resize',this.onScroll);this.onScroll();}
 componentDidUpdate(){this.onScroll();}
 componentWillUnmount(){window.removeEventListener('scroll',this.onScroll);window.removeEventListener('resize',this.onScroll);}
 // Как с пользовательским соглашением: «дальше» открывается, когда модуль долистан до конца
 onScroll(){const bar=document.getElementById('a-readbar');if(!bar)return;const h=document.documentElement,max=h.scrollHeight-h.clientHeight;bar.style.width=(max>0?Math.min(100,100*h.scrollTop/max):100)+'%';
  const id=this.state.view,end=document.getElementById('a-read-end');if(!end||this.state.read[id]||this.state.pr.done[id])return;if(end.getBoundingClientRect().top<=window.innerHeight)this.setState({read:{...this.state.read,[id]:true}});}
 save(pr){demoWrite('onboarding',pr);this.setState({pr});}
 open(view){this.setState({view,run:view==='test'?this.state.run:null});window.scrollTo(0,0);}
 setMe(me){demoWrite('candidate',me);this.setState({me});}
 renderVals(){const s=this.state,pr=s.pr,me=s.me,mods=ONB.modules,T=ONB.test,N=T.questions.length,nDone=mods.filter(m=>pr.done[m.id]).length,allDone=nDone===mods.length,passed=pr.best!=null&&pr.best>=T.pass;
  const i=mods.findIndex(m=>m.id===s.view),m=mods[i],isModule=!!me&&i>=0,isTest=!!me&&s.view==='test'&&allDone,isHub=!!me&&!isModule&&!isTest;
  const unlocked=isModule&&(pr.done[m.id]||s.read[m.id]),nxt=isModule?mods[i+1]:null;
  const run=s.run,inQ=!!run&&run.i<N,showRes=!!run&&run.i>=N,q=inQ?T.questions[run.i]:null,ans=inQ?run.answers[run.i]:null,answered=ans!=null;
  const score=run?run.answers.filter((a,k)=>a===T.questions[k].a).length:0;
  const v={noCandidate:!me,isHub,isModule,isTest,fillDemo:()=>this.setMe(DEMO_CANDIDATE),toHub:()=>this.open('hub'),
   hubTitle:ONB.title,hubIntro:ONB.intro,hubBar:'width:'+Math.round(100*nDone/mods.length)+'%',hubCount:nDone+' из '+mods.length,
   mods:mods.map((x,k)=>({title:x.title,minutes:x.minutes,mark:pr.done[x.id]?'✓':String(k+1),cls:pr.done[x.id]?'a-mod is-done':'a-mod',open:()=>this.open(x.id)})),
   testCls:'a-mod'+(passed?' is-done':'')+(allDone?'':' is-locked'),testMark:passed?'✓':String(mods.length+1),testTitle:T.title,testSub:N+' вопросов'+(allDone?'':' · откроется после всех шагов'),testLocked:!allDone,openTest:()=>this.open('test'),
   pills:mods.map((x,k)=>({n:k+1,title:x.title,cls:'a-pill'+(k===i?' is-on':(pr.done[x.id]?' is-done':'')),open:()=>this.open(x.id)})),
   modEyebrow:isModule?'Шаг '+(i+1)+' из '+mods.length+' · '+m.minutes+' мин':'',modTitle:isModule?m.title:'',
   isForm:isModule&&!!m.form,formIntro:FORM.matching.intro,
   fields:isModule&&m.form&&me?fieldViews(FORM.matching.fields,me,{},(id,val)=>this.setMe({...this.state.me,[id]:val}),s.ui,key=>this.setState({ui:{...this.state.ui,[key]:!this.state.ui[key]}})):[],
   blocks:isModule&&m.blocks?m.blocks.map(blockView):[],
   hasPrev:isModule&&i>0,prev:()=>this.open(mods[i-1].id),
   doneLocked:isModule&&!unlocked,doneCls:'btn btn-lg '+(unlocked?'btn-primary':'btn-subtle'),doneLabel:!isModule?'':(unlocked?(nxt?'Понятно, дальше':'Понятно, к тесту'):'Дочитайте до конца ↓'),
   done:()=>{if(!isModule)return;this.save({...pr,done:{...pr.done,[m.id]:true}});this.open(nxt?nxt.id:'test');},
   testIntro:isTest&&!run,testTitle:T.title,testText:T.intro,hasBest:pr.best!=null,bestLine:pr.best==null?'':pr.best+' из '+N+(passed?' — пройден':''),passed,startLabel:pr.attempts?'Пройти ещё раз':'Начать тест',
   start:()=>{this.setState({run:{i:0,answers:[]}});window.scrollTo(0,0);},
   testQuestion:isTest&&inQ,qNum:inQ?run.i+1:0,qTotal:N,qBar:'width:'+(inQ?Math.round(100*run.i/N):0)+'%',qText:q?q.q:'',
   qOpts:q?q.o.map((o,j)=>({text:o,locked:answered,cls:'a-answer'+(answered&&j===q.a?' is-right':'')+(answered&&j===ans&&ans!==q.a?' is-wrong':''),pick:()=>{const answers=[...run.answers];answers[run.i]=j;this.setState({run:{...run,answers}});}})):[],
   answered,explCls:answered&&ans===q.a?'hint':'error',explHead:answered&&ans===q.a?'Верно.':'Не совсем.',expl:q?q.e:'',nextQLabel:inQ&&run.i+1<N?'Следующий вопрос':'Посмотреть результат',
   nextQ:()=>{const r={...run,i:run.i+1};if(r.i>=N){const sc=r.answers.filter((a,k)=>a===T.questions[k].a).length;this.save({...pr,attempts:pr.attempts+1,best:Math.max(pr.best==null?0:pr.best,sc)});}this.setState({run:r});window.scrollTo(0,0);},
   testResult:isTest&&showRes,scoreLine:score+' из '+N,resultPassed:score>=T.pass,resultText:score>=T.pass?'Отлично, знакомство пройдено! Теперь можно выбрать время встречи с координатором.':'Нужно '+T.pass+' правильных ответов. Посмотрите разбор ниже и попробуйте ещё раз.',
   wrong:showRes?T.questions.map((x,k)=>({q:x.q,a:x.o[x.a],e:x.e,ok:run.answers[k]===x.a})).filter(x=>!x.ok):[]};
  v.hasWrong=v.wrong.length>0;return v;}
}
