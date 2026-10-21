// Вариант 3 «Темы»: шаг — короткий список тем, раскрываем по одной и отмечаем «Понятно»
const TOPIC_TITLES = { facts: 'Фонд в цифрах', timeline: 'Как всё начиналось', callout: 'Важно', rules: 'Пять правил', quiz: 'Проверьте себя', lead: 'Коротко' };
class Component extends DCLogic {
 constructor(p){super(p);this.state={me:ensureCandidate(),pr:loadProgress(),view:null,open:0,seen:{},quiz:{},run:null};}
 componentDidMount(){document.body.classList.add('a-static');}
 current(){const s=this.state,mods=ONB.modules;if(s.view==='test')return{test:true};if(s.view!=null)return{id:s.view,i:mods.findIndex(m=>m.id===s.view)};const i=mods.findIndex(m=>!s.pr.done[m.id]);return i<0?{test:true}:{id:mods[i].id,i};}
 save(pr){demoWrite('onboarding',pr);this.setState({pr});}
 renderVals(){const s=this.state,pr=s.pr,mods=ONB.modules,cur=this.current(),total=mods.length+1;
  const m=cur.test?null:mods[cur.i],stepN=cur.test?total:cur.i+1,nxt=m?mods[cur.i+1]:null;
  // Первый абзац шага — вводный текст, остальные блоки — темы списка
  const lead=m&&m.blocks[0].type==='lead'?m.blocks[0].text:'',rest=m?m.blocks.map((b,bi)=>({b,bi})).filter(x=>!(x.bi===0&&lead)):[];
  const seen=(m&&s.seen[m.id])||{},nSeen=rest.filter((_,j)=>seen[j]||pr.done[m.id]).length,all=!!m&&nSeen===rest.length;
  const mark=j=>{const ns={...seen,[j]:true},nextOpen=rest.findIndex((_,q)=>!ns[q]);this.setState({seen:{...s.seen,[m.id]:ns},open:nextOpen});};
  return {candidateUnlocked:interviewCurrent(interviewRead(),interviewIdentity(s.me))?.status==='completed',candidateLocked:interviewCurrent(interviewRead(),interviewIdentity(s.me))?.status!=='completed',candidateSection:'Знакомство',candidateName:fullName(s.me),candidateInitials:fullName(s.me).split(/\s+/).map(x=>x[0]).slice(0,2).join(''),stepLabel:'Знакомство с фондом · шаг '+stepN+' из '+total,
   segs:Array.from({length:total},(_,j)=>({cls:j<stepN-1?'is-done':(j===stepN-1?'is-on':'')})),
   isModule:!!m,isTest:!!cur.test,modTitle:m?m.title:'',lead,hasLead:!!lead,
   topics:rest.map(({b,bi},j)=>{const open=s.open===j,done=!!seen[j]||!!(m&&pr.done[m.id]);
    return {title:b.title||TOPIC_TITLES[b.type]||m.title,open,mark:done?'✓':String(j+1),cls:'l-item'+(open?' is-open':'')+(done?' is-seen':''),
     toggle:()=>this.setState({open:open?-1:j}),ok:()=>mark(j),
     blocks:[onbBlockView({...b,title:''},cur.i,m.blocks.slice(0,bi).filter(x=>x.type==='icards').length+cur.i,s.quiz,quiz=>this.setState({quiz}))]};}),
   seenLine:m?'Прочитано '+nSeen+' из '+rest.length:'',
   doneLocked:!!m&&!all,doneCls:'btn btn-lg '+(all?'btn-primary':'btn-subtle'),doneLabel:nxt?'Следующий шаг':'К тесту',
   done:()=>{if(!m||!all)return;this.save({...pr,done:{...pr.done,[m.id]:true}});this.setState({view:nxt?nxt.id:'test',open:0});window.scrollTo(0,0);},
   restart:()=>{this.save(freshProgress());this.setState({view:null,open:0,seen:{},quiz:{},run:null});},
   ...onbTestVals(this,!!cur.test)};}
}
