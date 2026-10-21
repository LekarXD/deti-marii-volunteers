// Вариант 2 «Карточки»: один блок на экран, листаем кнопкой «Дальше» — без длинной прокрутки
class Component extends DCLogic {
 constructor(p){super(p);this.state={me:ensureCandidate(),pr:loadProgress(),view:null,k:0,quiz:{},run:null};}
 componentDidMount(){document.body.classList.add('a-static');}
 current(){const s=this.state,mods=ONB.modules;if(s.view==='test')return{test:true};if(s.view!=null)return{id:s.view,i:mods.findIndex(m=>m.id===s.view)};const i=mods.findIndex(m=>!s.pr.done[m.id]);return i<0?{test:true}:{id:mods[i].id,i};}
 save(pr){demoWrite('onboarding',pr);this.setState({pr});}
 go(view,k){this.setState({view,k});window.scrollTo(0,0);}
 renderVals(){const s=this.state,pr=s.pr,mods=ONB.modules,cur=this.current(),total=mods.length+1;
  const m=cur.test?null:mods[cur.i],stepN=cur.test?total:cur.i+1,n=m?m.blocks.length:0,k=Math.min(s.k,Math.max(0,n-1)),last=m&&k===n-1,nxt=m?mods[cur.i+1]:null;
  const bi=m?m.blocks.slice(0,k).filter(x=>x.type==='icards').length+cur.i:0;
  return {stepLabel:'Знакомство с фондом · шаг '+stepN+' из '+total,
   segs:Array.from({length:total},(_,j)=>({cls:j<stepN-1?'is-done':(j===stepN-1?'is-on':'')})),
   isModule:!!m,isTest:!!cur.test,modTitle:m?m.title:'',cardCount:m?(k+1)+' / '+n:'',
   blocks:m?[onbBlockView(m.blocks[k],cur.i,bi,s.quiz,quiz=>this.setState({quiz}))]:[],
   hasBack:!!m&&(k>0||cur.i>0),back:()=>{if(k>0)this.go(m.id,k-1);else{const p=mods[cur.i-1];this.go(p.id,p.blocks.length-1);}},
   nextLabel:!m?'':(last?(nxt?'К следующему шагу':'К тесту'):'Дальше'),
   forward:()=>{if(!m)return;if(!last){this.go(m.id,k+1);return;}this.save({...pr,done:{...pr.done,[m.id]:true}});this.go(nxt?nxt.id:'test',0);},
   restart:()=>{this.save(freshProgress());this.setState({view:null,k:0,quiz:{},run:null});},
   ...onbTestVals(this,!!cur.test)};}
}
