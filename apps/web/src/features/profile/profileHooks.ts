import {useQuery} from '@tanstack/react-query';
import {api} from '../../api/transport';
import {keys} from '../../api/keys';
import type {components} from '../../api/generated/schema';
import {useAssignments} from '../activities/participationApi';
import type {ProfileTag} from './api';

type OpportunityPage=components['schemas']['OpportunityPage'];
type Assignment=components['schemas']['AssignmentParticipationView'];

const norm=(value:string)=>value.trim().toLocaleLowerCase('ru');
const distinct=(values:string[])=>[...new Map(values.map(value=>value.trim()).filter(value=>value&&value.length<=60).map(value=>[norm(value),value])).values()];

/** Published directions the volunteer can see. Their programs, audiences and places are exactly what matching compares profile picks with. */
export function useProfileCatalog(){
 const query=useQuery({queryKey:keys.list('profile-catalog',{limit:100}),staleTime:300000,queryFn:({signal})=>api<OpportunityPage>('/opportunities?limit=100',{signal})});
 const items=Array.isArray(query.data?.items)?query.data!.items:[];
 return {programs:distinct(items.map(item=>item.program??'')),audiences:distinct(items.map(item=>item.audience??'')),places:distinct(items.map(item=>item.location??''))};
}

/** Facts for the profile hero from the volunteer's own assignments: the first занятие they came to and their usual role. */
export function useVolunteerFacts(){
 const query=useAssignments(false);
 const items:Assignment[]=(query.data?.pages??[]).flatMap(page=>Array.isArray(page?.items)?page.items:[]);
 return volunteerFacts(items,Date.now());
}

export function volunteerFacts(items:Assignment[],now:number){
 const confirmed=items.filter(item=>item.status==='confirmed'&&!Number.isNaN(Date.parse(item.starts_at)));
 const since=confirmed.filter(item=>Date.parse(item.starts_at)<=now).sort((a,b)=>Date.parse(a.starts_at)-Date.parse(b.starts_at))[0]?.starts_at??null;
 const roles=new Map<string,{label:string;count:number;distance:number}>();
 for(const item of confirmed){
  const label=[item.role_title,item.title].map(part=>(part??'').trim()).filter(Boolean).filter((part,index,all)=>all.findIndex(other=>norm(other)===norm(part))===index).join(', ');
  if(!label)continue;
  const known=roles.get(label),distance=Math.abs(Date.parse(item.starts_at)-now);
  roles.set(label,{label,count:(known?.count??0)+1,distance:Math.min(known?.distance??Infinity,distance)});
 }
 const role=[...roles.values()].sort((a,b)=>b.count-a.count||a.distance-b.distance)[0]?.label??'';
 return {since,role};
}

/** Adds whole days to a calendar date (YYYY-MM-DD). */
export const addDays=(day:string,count:number)=>{const date=new Date(day+'T12:00:00Z');date.setUTCDate(date.getUTCDate()+count);return date.toISOString().slice(0,10);};

const kindOrder:ProfileTag['kind'][]=['skill','interest','age_interest','place_interest'];
/** One canonical order, so drafts and saved profiles compare by content. */
export const canonTags=(tags:ProfileTag[]=[])=>[...new Map(tags.map(tag=>[tag.kind+':'+norm(tag.label),{...tag,label:tag.label.trim()}])).values()].sort((a,b)=>kindOrder.indexOf(a.kind)-kindOrder.indexOf(b.kind)||a.label.localeCompare(b.label,'ru'));
export const sameLabel=(a:string,b:string)=>norm(a)===norm(b);
