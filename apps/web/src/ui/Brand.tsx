import {Link} from 'react-router-dom';
export function Brand({to='/',subtitle='волонтёры «Дети Марии»'}:{to?:string;subtitle?:string}){return <Link className="brand" to={to} aria-label="Опора — главная"><span className="mark" aria-hidden="true"><i/><i/><i/><i/></span><span><b>Опора</b><small>{subtitle}</small></span></Link>;}
