import type {ReviewQueueItem,ScenarioDraft,ScenarioStaff} from './api';

/** "[stage direction] line" → the direction (shown in italics) and the spoken text. */
export function splitLine(line:string|undefined){const m=/^\[(.+?)\]\s*([\s\S]*)$/.exec(line??'');return m?{dir:m[1],text:m[2]}:{dir:'',text:line??''};}
export const stripDir=(line:string|undefined)=>splitLine(line).text;
export function plural(n:number,[one,few,many]:[string,string,string]){const a=n%10,b=n%100;return a===1&&b!==11?one:a>=2&&a<=4&&(b<12||b>14)?few:many;}
/** «a», «a и b», «a, b и c». */
export function joinAnd(parts:string[]){return parts.length<2?parts.join(''):`${parts.slice(0,-1).join(', ')} и ${parts.at(-1)}`;}
export const initials=(name:string)=>name.trim().split(/\s+/).map(part=>part[0]??'').join('').slice(0,2).toUpperCase()||'?';
const tones=['ph-b','ph-o','ph-v','ph-g','ph-p'];
export const toneOf=(seed:string)=>tones[[...seed].reduce((sum,char)=>sum+char.charCodeAt(0),0)%tones.length];
/** «Сегодня, 11:40», «Вчера, 16:05», «20 октября». */
export function whenText(iso:string|null|undefined,now=new Date()){
 if(!iso)return '';const date=new Date(iso);const day=(value:Date)=>new Date(value.getFullYear(),value.getMonth(),value.getDate()).getTime();
 const diff=Math.round((day(now)-day(date))/86400000);const time=date.toLocaleTimeString('ru-RU',{hour:'2-digit',minute:'2-digit'});
 return diff===0?`Сегодня, ${time}`:diff===1?`Вчера, ${time}`:date.toLocaleDateString('ru-RU',{day:'numeric',month:'long'});
}

export const emptyDraft=(draft:Partial<ScenarioDraft>&{title:string}):Required<ScenarioDraft>=>({character_name:'',character_profile:'',situation:'',first_turn:'',warning:'',methods:[],hints:[],criteria:[],evaluation_cases:[],...draft} as Required<ScenarioDraft>);

/** What the API still needs before the psychologist can approve (mirrors ensure_draft_ready). */
export function missingParts(draft:ScenarioDraft){
 const out:string[]=[];const blank=(value?:string)=>!value?.trim();
 if(blank(draft.character_name))out.push('имя ребёнка');if(blank(draft.character_profile))out.push('возраст и история');if(blank(draft.situation))out.push('ситуация');if(blank(draft.first_turn))out.push('первая фраза');
 const criteria=draft.criteria??[],cases=draft.evaluation_cases??[];
 if(!criteria.length)out.push('критерии');
 if(cases.length<2)out.push('два эталона');
 else if(criteria.length&&cases.some(example=>criteria.some(criterion=>example.expected_scores[criterion.key]===undefined)))out.push('оценки в эталонах');
 return out;
}
/** A field the API rejects outright, so the draft cannot be saved yet. */
export function saveProblem(draft:ScenarioDraft){
 if(!draft.title.trim())return 'Нужно название';
 const criteria=draft.criteria??[];const criterion=criteria.findIndex(row=>!row.title.trim()||!row.guidance.trim());
 if(criterion>=0)return `Заполните критерий ${criterion+1}`;
 const cases=draft.evaluation_cases??[];const example=cases.findIndex(row=>!row.title.trim()||row.turns.length<2||row.turns.some(turn=>!turn.content.trim())||!row.turns.some(turn=>turn.speaker==='volunteer'));
 if(example>=0)return `Допишите эталон ${example+1}`;
 return '';
}

export type Stage='draft'|'review'|'approved'|'tested'|'published';
export interface ReviewRow {id:string;draft_version:number;decision:'approved'|'changes_requested';reason:string;at:string}
export interface TestRow {id:string;draft_version:number;state:string;at:string}
export const reviewsOf=(item:ScenarioStaff)=>item.reviews as unknown as ReviewRow[];
export const testsOf=(item:ScenarioStaff)=>item.test_runs as unknown as TestRow[];
export const isRunning=(test?:TestRow)=>!!test&&['queued','running'].includes(test.state);
/** Volunteers see exactly the current draft: publishing bumps the draft revision by one and nothing changed since. */
export const isLive=(item:ScenarioStaff)=>!!item.publication_id&&item.published_draft_version!=null&&item.version===item.published_draft_version+1;
/** There is no stored status: the stage follows from the latest review and test run of the current draft revision. */
export function flowOf(item:ScenarioStaff,draft:ScenarioDraft=item.draft,dirty=false){
 const review=reviewsOf(item).find(row=>Number(row.draft_version)===item.version);
 const test=testsOf(item).find(row=>Number(row.draft_version)===item.version);
 const missing=missingParts(draft);
 const stage:Stage=dirty?'draft':isLive(item)?'published':review?.decision==='changes_requested'?'draft':review?.decision==='approved'?(test&&!isRunning(test)?'tested':'approved'):missing.length?'draft':'review';
 return {stage,review,test,missing,returned:!dirty&&review?.decision==='changes_requested'?review.reason:''};
}
/** Status dot on a scenario card; a live scenario needs none. */
export function cardStatus(item:ScenarioStaff){
 const {stage}=flowOf(item);
 if(stage==='review')return {label:'у психолога',dot:'dot dot-orange'};
 if(item.publication_id)return null;
 if(item.archived_at)return {label:'снят',dot:'dot'};
 return stage==='draft'?{label:'черновик',dot:'dot'}:{label:'одобрен',dot:'dot dot-green'};
}
export const passedText=(count:number)=>count?`${count} ${plural(count,['прошёл','прошли','прошли'])}`:'ещё никто не проходил';
export const openItem=(row:ReviewQueueItem)=>row.state!=='resolved';
/** «3 попытки ждут разбора» and what they are: appeals, zeros on a critical criterion, requests for support. */
export function queueSummary(appeals:ReviewQueueItem[],support:ReviewQueueItem[]){
 const total=appeals.length+support.length,critical=appeals.filter(row=>row.critical).length,plain=appeals.length-critical;
 return {total,title:`${total} ${plural(total,['попытка ждёт','попытки ждут','попыток ждут'])} разбора`,
  line:joinAnd([plain?`${plain} ${plural(plain,['апелляция','апелляции','апелляций'])} на оценку ИИ`:'',critical?`${critical} с ошибкой в критичном`:'',support.length?`${support.length} ${plural(support.length,['просьба','просьбы','просьб'])} о поддержке`:''].filter(Boolean))};
}

