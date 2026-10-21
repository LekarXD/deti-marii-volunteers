import {Link,Outlet,useLocation} from 'react-router-dom';
import {Brand} from '../ui';
import './public.css';
export function PublicLayout(){const application=useLocation().pathname==='/apply';return <div className="dm public-app"><header className="opora-header">{application?<Link className="brand" to="/"><span className="mark" aria-hidden="true"><i/><i/><i/><i/></span><span><b>Дети Марии</b><small>благотворительный фонд</small></span></Link>:<Brand to="/"/>}<span className="public-note">{application?'mariaschildren.ru, Стать волонтёром':''}</span></header><main id="main-content"><Outlet/></main></div>;}
