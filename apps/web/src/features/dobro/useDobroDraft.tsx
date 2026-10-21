import {useEffect,useState} from 'react';
import {Button} from '../../ui';
function equal<T extends {version?:number}>(a:T,b:T){return JSON.stringify({...a,version:undefined})===JSON.stringify({...b,version:undefined});}
/** Refetches update a clean editor, never silently discard a person's draft. */
export function useDobroDraft<T extends {version?:number}>(server:T){
 const [state,setState]=useState({base:server,draft:server});
 useEffect(()=>{setState(current=>current.base.version!==server.version&&(equal(current.draft,current.base)||equal(current.draft,server))?{base:server,draft:server}:current);},[server]);
 const dirty=!equal(state.draft,state.base),conflict=dirty&&state.base.version!==server.version&&!equal(state.draft,server);
 return {draft:state.draft,dirty,conflict,setDraft:(draft:T)=>setState(current=>({...current,draft})),useServer:()=>setState({base:server,draft:server}),keepMine:()=>setState(current=>({base:server,draft:{...current.draft,version:server.version}}))};
}
export function DobroDraftConflict({useServer,keepMine}:{useServer:()=>void;keepMine:()=>void}){return <div role="status" className="dobro-draft-conflict"><p>Данные изменились в другом окне. Ваш текст остался в форме. Сверьте его перед сохранением.</p><div className="actions"><Button variant="secondary" onClick={keepMine}>Оставить мой текст</Button><Button variant="ghost" onClick={useServer}>Обновить из сохранённого</Button></div></div>;}
