import {useState} from 'react';
import {Button,Card,ErrorState,Field,Input,LoadingState} from '../../ui';
import {useDobroQuery,useDobroCommand} from './api';
import type {components} from '../../api/generated/schema';
import {ApiError} from '../../api/transport';
type Profile=components['schemas']['DobroProfileView'];
/** CRM volunteer UUID, deliberately never an email or guessed login identity. */
export function DobroVolunteerProfile({volunteerId}:{volunteerId:string}){const path=`/fund/volunteers/${volunteerId}/external-profiles/dobro`,query=useDobroQuery<Profile>('volunteer-profile',path);return query.isPending?<LoadingState/>:query.error instanceof ApiError&&query.error.code==='dobro_account_unlinked'?<Card className="dobro-section"><h3 className="h3">Профиль на Добро.рф</h3><p>{query.error.message}</p></Card>:query.error?<ErrorState error={query.error} retry={()=>void query.refetch()}/>:<Editor key={query.data.version} path={path} profile={query.data}/>;}
function Editor({path,profile}:{path:string;profile:Profile}){const [url,setUrl]=useState(profile.profile_url),save=useDobroCommand(path,'PUT');return <Card className="dobro-section"><h3 className="h3">Профиль на Добро.рф</h3><form onSubmit={event=>{event.preventDefault();void save.mutateAsync({profile_url:url,expected_version:profile.version}).catch(()=>{});}}><Field label="Ссылка на профиль волонтёра" hint="Необязательно. Добро.рф не влияет на участие в занятиях."><Input type="url" value={url} onChange={event=>setUrl(event.target.value)} maxLength={1500}/></Field><Button type="submit" variant="secondary" disabled={url===profile.profile_url} loading={save.isPending}>Сохранить профиль</Button>{save.error&&<ErrorState error={save.error}/>}</form></Card>;}
