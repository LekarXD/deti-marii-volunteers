import {Link} from 'react-router-dom';
import {Card} from '../../ui';
import {useDobroQuery,monthNow,type DobroPeriod} from './api';
import './dobro.css';
const plural=(count:number,one:string,few:string,many:string)=>{const form=new Intl.PluralRules('ru-RU').select(count);return `${count} ${form==='one'?one:form==='few'?few:many}`;};
const monthName=(period:string)=>new Date(period+'-15T12:00:00+03:00').toLocaleDateString('ru-RU',{month:'long',timeZone:'Europe/Moscow'});
const dayMonth=(value:string)=>new Date(value+'T12:00:00+03:00').toLocaleDateString('ru-RU',{day:'numeric',month:'long',timeZone:'Europe/Moscow'});
export function DobroOverviewTask(){const period=monthNow(),query=useDobroQuery<DobroPeriod>('overview',`/fund/integrations/dobro/transfers?period=${period}`);if(!query.data)return null;const view=query.data,month=monthName(period);return <Card className="dobro-overview"><div><h3 className="h3">Внести часы за {month} в Добро.рф</h3><p>{view.total_hours_due?`${plural(view.total_hours_due,'час','часа','часов')} у ${plural(view.total_people,'человека','человек','человек')}. Внесите их до ${dayMonth(view.work_deadline)}.`:`За ${month} вносить нечего: часы уже отмечены или участий пока не было.`}</p>{view.at_risk_count>0&&<p className="err">Срочно: {plural(view.at_risk_count,'запись','записи','записей')} с близким или пропущенным крайним сроком</p>}</div><Link className="btn btn-secondary" to={`/fund/integrations/dobro/transfers?period=${period}`}>Открыть список</Link></Card>;}
