import {Outlet, useLocation} from 'react-router-dom';
import {Brand} from '../ui';
import {useSession} from './layouts';
import {AccountControl} from './layouts/AccountControl';
import './public.css';
// The anonymous entry page carries its own logo inside the sign-in card, so it skips the header.
export function PublicLayout(){const {session}=useSession();const signedIn=Boolean(session?.user_id);const {pathname}=useLocation();const entry=!signedIn&&pathname==='/';return <div className={entry?'dm public-app public-app-entry':'dm public-app'}>{!entry&&<header className="opora-header"><Brand to={signedIn&&session?.is_staff?'/fund':'/'} subtitle="Благотворительный фонд «Дети Марии»"/>{signedIn&&<div className="public-account"><AccountControl/></div>}</header>}<main id="main-content"><Outlet/></main></div>;}
