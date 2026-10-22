import {DobroSettingsPanel} from '../dobro';
import {useSearchParams} from 'react-router-dom';
import {Card,Combobox,ErrorState,LoadingState} from '../../ui';
import {AISettingsPanel} from '../knowledge/AISettingsPanel';
import {NotificationAdminPage} from '../notifications/NotificationAdminPage';
import {readReadiness,type Readiness} from '../notifications/api';
import {useQuery} from '@tanstack/react-query';
import {keys} from '../../api/keys';
import {StaffPanel} from './StaffPanel';
import {AuditPanel} from './AuditPanel';
import {SignalRulesPanel} from './SignalRulesPanel';
import './admin.css';
const sections=[{id:'roles',label:'Роли и доступы'},{id:'channels',label:'Уведомления'},{id:'integrations',label:'Интеграции'},{id:'ai',label:'ИИ и приватность'},{id:'rules',label:'Правила сигналов'},{id:'audit',label:'Журнал'}];
export function AdminPage(){const [params,setParams]=useSearchParams(),requested=params.get('section'),tab=sections.some(section=>section.id===requested)?requested!:'roles';return <div className="admin-page"><h1 className="h1">Настройки</h1><nav className="admin-tabs" aria-label="Разделы настроек">{sections.map(section=><button key={section.id} aria-current={tab===section.id?'page':undefined} className={tab===section.id?'is-current':''} onClick={()=>setParams({section:section.id})}>{section.label}</button>)}</nav><div className="admin-section-picker"><Combobox label="Раздел настроек" value={tab} onChange={value=>setParams({section:value})} options={sections.map(section=>({value:section.id,label:section.label}))}/></div><div className="admin-body">{tab==='roles'?<StaffPanel/>:tab==='channels'?<NotificationAdminPage/>:tab==='integrations'?<IntegrationPanel/>:tab==='ai'?<AISettingsPanel/>:tab==='audit'?<AuditPanel/>:<SignalRulesPanel/>}</div></div>;}
function IntegrationPanel(){const query=useQuery<Readiness>({queryKey:keys.self('notification-readiness'),queryFn:({signal})=>readReadiness(signal),refetchInterval:30000});return <><h2 className="h2">Интеграции</h2><p>Состояние каналов подтверждается сервером. Ключи и секреты на этой странице не показываются.</p>{query.isPending?<LoadingState/>:query.error?<ErrorState error={query.error} retry={()=>void query.refetch()}/>:query.data?.channels.map(channel=><Card key={channel.channel}><div className="section-head"><h3 className="h3">{channel.channel==='in_app'?'Личный кабинет':channel.channel==='email'?'Электронная почта':channel.channel}</h3><span className="tag">{channel.state==='available'?'Доступно':channel.state==='development_only'?'Локальный режим':'Недоступно'}</span></div><p>{channel.reason}</p></Card>)}<DobroSettingsPanel/></>;}
