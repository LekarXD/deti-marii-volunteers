import {useQuery} from '@tanstack/react-query';
import {api} from '../../api/transport';
import {keys} from '../../api/keys';
import type {components} from '../../api/generated/schema';

const POLL=60_000;
const day=(offset:number)=>new Date(Date.now()+offset*86_400_000).toISOString().slice(0,10);
/** «1 приглашение», «2 приглашения», «5 приглашений». */
export function plural(count:number,[one,few,many]:readonly [string,string,string]){const tens=count%100,units=count%10;return tens>10&&tens<20?many:units===1?one:units>=2&&units<=4?few:many;}
const labels:Record<string,readonly [string,string,string]>={'/my/schedule':['приглашение','приглашения','приглашений'],'/messages':['новое сообщение','новых сообщения','новых сообщений']};
/** Spoken form of a section counter, e.g. «2 новых сообщения». */
export const countLabel=(to:string,count:number)=>`${count} ${plural(count,labels[to]??['','',''])}`.trim();

/** Coordinator invitations waiting for the volunteer's own answer; a sign-up waiting for the coordinator is not counted. */
async function invitations(signal:AbortSignal){
 const page=await api<components['schemas']['AssignmentParticipationPage']>(`/me/schedule?from=${day(-1)}&to=${day(90)}&timezone=Europe/Moscow&state=active&limit=100`,{signal});
 const now=Date.now();
 return page.items.filter(item=>item.status==='invited'&&(item.origin??'invitation')==='invitation'&&item.occurrence_status==='scheduled'&&new Date(item.ends_at).getTime()>now).length;
}
async function unreadMessages(signal:AbortSignal){
 const page=await api<components['schemas']['ConversationPage']>('/conversations?limit=30',{signal});
 return page.items.reduce((sum,item)=>sum+Math.max(item.unread_count,0),0);
}

/** Orange counters next to «Мероприятия» and «Сообщения»; keyed by section path, zero means no counter.
 * The keys sit under the activities and conversations prefixes, so those screens' invalidations refresh them too. */
export function useVolunteerCounts():Record<string,number>{
 const invited=useQuery({queryKey:keys.list('activities',{kind:'nav-invitations'}),queryFn:({signal})=>invitations(signal),refetchInterval:POLL,refetchIntervalInBackground:false});
 const unread=useQuery({queryKey:keys.list('messaging-conversations',{kind:'nav-unread'}),queryFn:({signal})=>unreadMessages(signal),refetchInterval:POLL,refetchIntervalInBackground:false});
 return {'/my/schedule':invited.data??0,'/messages':unread.data??0};
}
