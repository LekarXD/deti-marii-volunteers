import {useQuery} from '@tanstack/react-query';
import type {components} from '../../api/generated/schema';
import {api} from '../../api/transport';
import {Dialog,LoadingState,ErrorState} from '../../ui';
import './summary.css';
export function SummaryPublishedDialog({webinarId,onClose}:{webinarId:string;onClose:()=>void}){
 const query=useQuery({queryKey:['webinar-summary-published',webinarId],queryFn:({signal})=>api<components['schemas']['SummaryRevisionView']>(`/webinars/${webinarId}/summary/published`,{signal}),refetchInterval:15000});
 return <Dialog open className="summary-dialog" onClose={onClose} title="Итоги занятия">{query.isLoading?<LoadingState/>:query.error?<ErrorState error={query.error} retry={()=>void query.refetch()}/>:query.data&&<article className="summary-preview"><h3>{query.data.title}</h3><p>{query.data.body}</p></article>}</Dialog>;
}
