import {Link} from 'react-router-dom';
import fundLogo from '../assets/fund/marias-children-logo.svg';
import './Brand.css';
export function Brand({to='/',subtitle='волонтёры «Дети Марии»'}:{to?:string;subtitle?:string}){
 return <Link className="brand brand-fund" to={to} aria-label="Дети Марии — главная" title={subtitle}><img className="brand-fund-logo" src={fundLogo} alt="Дети Марии" width="324" height="64"/><span className="brand-fund-context">{subtitle}</span></Link>;
}
