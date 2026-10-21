import {Link} from 'react-router-dom';
import {Card} from '../../ui';
import {useDobroQuery,monthNow,type DobroPeriod,dobroDate} from './api';
import './dobro.css';
export function DobroOverviewTask(){const period=monthNow(),query=useDobroQuery<DobroPeriod>('overview',`/fund/integrations/dobro/transfers?period=${period}`);if(!query.data)return null;const view=query.data;return <Card className="dobro-overview"><div><h3 className="h3">Перенести часы в Добро.рф</h3><p>{view.total_hours_due?`${view.total_hours_due} ч у ${view.total_people} человек`:'Все рассчитанные часы отмечены или пока нет фактов участия'}, рабочий срок {dobroDate(view.work_deadline)}</p>{view.at_risk_count>0&&<p className="err">Близок срок или есть просрочка: {view.at_risk_count} строк</p>}</div><Link className="btn btn-secondary" to={`/fund/integrations/dobro/transfers?period=${period}`}>Открыть перенос</Link></Card>;}
