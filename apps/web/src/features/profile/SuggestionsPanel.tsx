import {Button,Icon} from '../../ui';
import {Suggestion,useProfileList,useProfileCommand} from './api';

const labels:Record<string,string>={about:'О себе',skills:'Что умею',interests:'Что люблю'};
const render=(value:unknown)=>Array.isArray(value)?value.join(', '):String(value??'');
const failureText=(error:unknown)=>error instanceof Error&&error.message?error.message:'Не получилось. Попробуй ещё раз.';
function useSuggestions(){const query=useProfileList<Suggestion>('suggestions','/me/profile/suggestions');return Array.isArray(query.data)?query.data:[];}

/** One AI proposal waiting for the volunteer, as a single box. Nothing is shown when there is none. */
export function SuggestionBox({version,onChanged}:{version:number;onChanged:()=>void}){
 const suggestion=useSuggestions().find(item=>item.state==='proposed');
 if(!suggestion)return null;
 return <ProposedBox key={suggestion.id} suggestion={suggestion} version={version} onChanged={onChanged}/>;
}

function ProposedBox({suggestion,version,onChanged}:{suggestion:Suggestion;version:number;onChanged:()=>void}){
 const command=useProfileCommand<Suggestion>(`/me/profile/suggestions/${suggestion.id}/decision`),stale=version!==suggestion.base_version;
 const decide=(decision:'accept'|'reject')=>void command.mutateAsync({expected_version:version,decision}).then(onChanged).catch(()=>{});
 const sources=suggestion.source_refs.map(source=>String(source.fragment??'').trim()).filter(Boolean);
 return <section className="ai-box prof-ai" aria-labelledby={'suggestion-'+suggestion.id}>
  <div className="row prof-ai-head"><span className="prof-ai-mark" aria-hidden="true"><Icon name="sparkle"/></span><h2 className="h3" id={'suggestion-'+suggestion.id}>Можно дополнить профиль</h2></div>
  {Object.entries(suggestion.patch).map(([key,value])=><div className="prof-ai-field" key={key}><span className="label">{labels[key]||key}</span><p className="p">{render(value)}</p></div>)}
  {sources.length>0&&<details className="prof-details"><summary>Откуда это</summary><ul className="prof-quotes">{sources.map((fragment,index)=><li key={index}><q>{fragment}</q></li>)}</ul></details>}
  {stale&&<p className="p">Профиль уже изменился, поэтому это предложение устарело.</p>}
  <div className="actions"><Button disabled={command.isPending||stale} onClick={()=>decide('accept')}>Принять</Button><Button variant="ghost" disabled={command.isPending} onClick={()=>decide('reject')}>Не надо</Button></div>
  {command.error&&<p className="err" role="alert">{failureText(command.error)}</p>}
 </section>;
}

/** Accepted proposals stay revertible from «Приватность». */
export function AcceptedSuggestions({version,onChanged}:{version:number;onChanged:()=>void}){
 const accepted=useSuggestions().filter(item=>item.state==='accepted');
 if(!accepted.length)return null;
 return <section className="card"><h2 className="h3 prof-card-title">Принятые подсказки</h2><div className="rows">{accepted.map(item=><AcceptedRow key={item.id} suggestion={item} version={version} onChanged={onChanged}/>)}</div></section>;
}

function AcceptedRow({suggestion,version,onChanged}:{suggestion:Suggestion;version:number;onChanged:()=>void}){
 const command=useProfileCommand<Suggestion>(`/me/profile/suggestions/${suggestion.id}/decision`);
 return <div className="rowi">
  <div className="grow"><span className="rowi-title">{Object.keys(suggestion.patch).map(key=>labels[key]||key).join(', ')}</span><span className="meta">{new Date(suggestion.created_at).toLocaleDateString('ru',{day:'numeric',month:'long'})}</span>{command.error&&<span className="err" role="alert">{failureText(command.error)}</span>}</div>
  <span className="rowi-end"><Button variant="ghost" size="sm" disabled={command.isPending} onClick={()=>void command.mutateAsync({expected_version:version,decision:'revert'}).then(onChanged).catch(()=>{})}>Отменить</Button></span>
 </div>;
}
