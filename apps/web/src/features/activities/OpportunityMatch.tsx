import {Link} from 'react-router-dom';
import type {Opportunity} from './api';

const missingLabels:Record<string,string>={
  interests:'Выбранные интересы не указаны',
  skills:'Выбранные навыки не указаны',
  availability:'Время доступности не указано',
  occurrence_time:'Совместимость по времени не проверена: у возможности нет точной даты и времени',
  preparation:'Часть подготовки ещё не подтверждена',
};
const sourceLabels:Record<string,string>={skills:'Навыки профиля',interests:'Интересы профиля',program:'Программа',audience:'Аудитория',location:'Место',role_title:'Версия роли',preparation:'Версия подготовки'};

export function OpportunityMatch({item}:{item:Opportunity}){
  const match=item.matching;
  return <section className="activity-match">
    <h3 className="h3">Что известно о подборе</h3>
    {match.reasons.length?<ul>{match.reasons.map(reason=><li key={reason}>{reason}</li>)}</ul>:<p className="meta">Подтверждённых совпадений с выбранными данными профиля пока нет.</p>}
    {match.constraints.length>0&&<><h4>Что нужно учесть</h4><ul>{match.constraints.map(value=><li key={value}>{value}</li>)}</ul></>}
    {match.missing_data.length>0&&<><h4>Что ещё не проверено</h4><ul className="meta">{match.missing_data.map(value=><li key={value}>{missingLabels[value]??value}</li>)}</ul></>}
    <p className="meta">Совпадение названий — повод посмотреть условия. Подтверждение участия и подготовка проверяются отдельно.</p>
    <Link to="/profile">Уточнить профиль</Link>
    {!!match.evidence?.length&&<details><summary>Источники объяснения</summary>
      <p className="meta">Профиль: версия {match.context_versions?.profile??'не указана'}. Доступность: версия {match.context_versions?.availability??'не указана'}.</p>
      {match.evidence.map((source,index)=><p className="meta activity-match-source" key={index}>{sourceLabels[source.field]??source.field}, версия {source.version}, {source.source_id}</p>)}
    </details>}
  </section>;
}
