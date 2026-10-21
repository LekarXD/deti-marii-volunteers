import {useState} from 'react';
import {Button,Card,Combobox,ErrorState,LoadingState} from '../../ui';
import {useOpportunityList} from '../activities/api';
import {useDobroQuery,useDobroCommand,type DobroSeries} from './api';
import './dobro.css';
export function EventOpportunityPicker({seriesId}:{seriesId:string}){
 const path=`/fund/event-series/${seriesId}/dobro-opportunity`,query=useDobroQuery<DobroSeries>('event-opportunity',path),list=useOpportunityList(true),[selected,setSelected]=useState(''),save=useDobroCommand<DobroSeries>(path,'PUT');
 const choices=list.data?.pages.flatMap(page=>page.items).map(item=>({value:item.id,label:item.title}))??[];
 if(query.isPending)return <LoadingState/>;
 if(query.error)return <ErrorState error={query.error} retry={()=>void query.refetch()}/>;
 const current=query.data,value=selected||current.opportunity_id||'';
 if(current.opportunity_id&&!choices.some(item=>item.value===current.opportunity_id))choices.unshift({value:current.opportunity_id,label:current.opportunity_title});
 return <Card className="dobro-section"><h3 className="h3">Возможность для учёта часов</h3><p>Свяжите эту серию событий с возможностью. Её ссылка на Добро.рф будет использоваться для всех ролей в составе.</p><Combobox label="Волонтёрская возможность" value={value} onChange={setSelected} options={choices} disabled={current.locked||save.isPending} searchable/>{list.hasNextPage&&<Button variant="ghost" onClick={()=>void list.fetchNextPage()} loading={list.isFetchingNextPage}>Показать ещё возможности</Button>}{list.error&&<ErrorState error={list.error} retry={()=>void list.refetch()}/>}{current.locked?<p className="meta">В серии уже есть факты участия. Привязка сохранена для истории; для другого направления создайте новую серию.</p>:<Button variant="secondary" loading={save.isPending} disabled={!value||value===current.opportunity_id} onClick={()=>void save.mutateAsync({opportunity_id:value,expected_version:current.version}).then(()=>setSelected('')).catch(()=>{})}>Сохранить привязку</Button>}{save.error&&<ErrorState error={save.error}/>}</Card>;
}
