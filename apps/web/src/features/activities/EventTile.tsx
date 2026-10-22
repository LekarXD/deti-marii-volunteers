import type {ReactNode} from 'react';
import {Link} from 'react-router-dom';
import {Icon} from '../../ui';
import {multiplierLabel} from './participationApi';
import {cardMultiplier,cardPlaces,eventIcon,tileWhen,toneFor,type EventCard,type Places} from './eventsApi';
import './events.css';

/** The one event tile (canvas Events/Home/Mine): art in the event's tone, title, start, places dot; the points pill takes the arrow's place. */
export function PlacesDot({places}:{places:Places}){return <span className={`places${places.tone?` ${places.tone}`:''}`}><i aria-hidden="true"/>{places.label}</span>}
export function PointsPill({value}:{value:number}){return value>1?<span className="ev-pts"><Icon name="star"/>{multiplierLabel(value)}</span>:null}
export function EventTile({card,arrow=true}:{card:EventCard;arrow?:boolean}){
 const multiplier=cardMultiplier(card);
 return <Link className={`tile${card.full||card.conflict?' is-off':''}`} to={`/events/${card.occurrence_id}`}>
  <span className={`art ${toneFor(card.title).art}`} aria-hidden="true"><Icon name={eventIcon(card)}/></span>
  <span className="h3">{card.title}</span>
  <span className="when">{tileWhen(card)}</span>
  <span className="tile-foot"><PlacesDot places={cardPlaces(card)}/>{multiplier>1?<PointsPill value={multiplier}/>:arrow&&<Icon name="arrow-right"/>}</span>
 </Link>;
}
/** «Почему так»: the server's personal reasons for the top three cards; without any, the general rule. */
export function WhyCards({cards,fallback}:{cards:EventCard[];fallback:ReactNode}){
 const explained=cards.filter(card=>card.reasons.length).slice(0,3);
 return explained.length?<ul className="ev-why-list">{explained.map(card=><li key={card.occurrence_id}><span className="strong">{card.title}</span><ul>{card.reasons.map(reason=><li key={reason}>{reason}</li>)}</ul></li>)}</ul>:<p className="p">{fallback}</p>;
}
