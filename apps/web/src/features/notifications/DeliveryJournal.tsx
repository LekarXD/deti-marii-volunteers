import {useState} from 'react';
import {useInfiniteQuery} from '@tanstack/react-query';
import {keys} from '../../api/keys';
import {Button,Card,EmptyState,ErrorState,LoadingState} from '../../ui';
import {channelLabel,dateTime,readAttempts,readDeliveries,type Delivery,type AttemptPage} from './api';
const states:Record<string,string>={queued:'В очереди',processing:'Обрабатывается',calling:'Запрос провайдеру',accepted:'Принято почтовым сервером',delivered:'Доставлено',rejected:'Отклонено',bounced:'Письмо возвращено',unknown:'Результат отправки неизвестен',unavailable:'Отправка недоступна',dev_inbox:'В локальном dev-inbox',deferred_quiet:'Отложено до окончания тихих часов',waiting_identity:'Ожидает подтверждения адреса'};
export function deliveryState(state:string){return states[state]??(state.startsWith('suppressed_')?'Остановлено текущими правилами':state);}
export function DeliveryJournal(){
 const rows=useInfiniteQuery({queryKey:keys.list('notification-deliveries'),queryFn:({pageParam,signal})=>readDeliveries(pageParam,signal),initialPageParam:null as string|null,getNextPageParam:last=>last.next_cursor??undefined,staleTime:0,refetchInterval:15000});
 if(rows.isPending)return <LoadingState/>;if(rows.error)return <ErrorState error={rows.error} retry={()=>rows.refetch()}/>;
 return <div className="notification-stack"><p className="meta">«Принято почтовым сервером» означает приём письма провайдером. Подтверждённая доставка отображается отдельно. Неизвестный результат требует проверки.</p>{rows.data.pages[0].items.length?rows.data.pages.flatMap(p=>p.items).map(row=><DeliveryRow key={row.id} row={row}/>):<Card><EmptyState title="Журнал пока пуст" description="Здесь появятся реальные попытки доставки после постановки уведомлений в очередь."/></Card>}{rows.hasNextPage&&<Button variant="secondary" loading={rows.isFetchingNextPage} onClick={()=>rows.fetchNextPage()}>Ещё уведомления</Button>}</div>;
}
function DeliveryRow({row}:{row:Delivery}){
 const [open,setOpen]=useState(false);
 const attempts=useInfiniteQuery({queryKey:keys.detail('notification-attempts',`${row.id}:${row.version}`),queryFn:({pageParam,signal})=>readAttempts(row.id,pageParam!,signal),initialPageParam:row.attempts_next_cursor,getNextPageParam:last=>last.next_cursor??undefined,enabled:false});
 const pages:AttemptPage[]=attempts.data?.pages??[];
 return <Card><div className="notification-row"><div><p className="meta">{channelLabel(row.channel)}</p><h3 className="h3">{deliveryState(row.state)}</h3>{row.next_attempt_at&&<p className="meta">Следующая попытка: {dateTime(row.next_attempt_at)}</p>}<p className="meta notification-code">Запись {row.id}</p></div><Button variant="secondary" aria-expanded={open} onClick={()=>setOpen(v=>!v)}>{open?'Свернуть':'Попытки доставки'}</Button></div>{open&&<><ol className="notification-attempts">{[...row.attempts,...pages.flatMap(p=>p.items)].map(attempt=><li key={attempt.attempt_number}><b>Попытка {attempt.attempt_number} · {deliveryState(attempt.state)}</b><p className="meta">{dateTime(attempt.started_at)}{attempt.completed_at?` — ${dateTime(attempt.completed_at)}`:''}</p>{attempt.error_code&&<p className="meta">Код результата: {attempt.error_code}</p>}</li>)}</ol>{!row.attempts.length&&<p className="meta">Попыток пока не было.</p>}{attempts.error?<ErrorState error={attempts.error}/>:null}{row.attempts_next_cursor!==null&&(!attempts.data||attempts.hasNextPage)&&<Button variant="ghost" loading={attempts.isFetching} onClick={()=>attempts.fetchNextPage()}>Предыдущие попытки</Button>}</>}</Card>;
}
