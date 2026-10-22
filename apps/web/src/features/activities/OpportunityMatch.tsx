import {Link} from 'react-router-dom';
import {Icon} from '../../ui';
import type {Opportunity} from './api';

/** What the direction shares with the volunteer's form, as plain rows; no versions or sources. */
export function OpportunityMatch({item}:{item:Opportunity}){
  const {reasons,constraints}=item.matching;
  if(!reasons.length&&!constraints.length)return null;
  return <div className="card action-card">
    <h2 className="h3">{reasons.length?'Совпадает с анкетой':'Что учесть'}</h2>
    <div className="rows">
      {reasons.map(reason=><div className="rowi" key={reason}><span className="st st-ok" aria-hidden="true"><Icon name="check"/></span><span>{reason}</span></div>)}
      {constraints.map(value=><div className="rowi" key={value}><span className="st st-wait" aria-hidden="true"><Icon name="alert"/></span><span>{value}</span></div>)}
    </div>
    <p className="p">Интересы и время можно поменять в <Link to="/profile">профиле</Link>.</p>
  </div>;
}
