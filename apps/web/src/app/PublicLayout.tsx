import {Outlet} from 'react-router-dom';
import {Brand} from '../ui';
import {useSession} from './layouts';
import {AccountControl} from './layouts/AccountControl';
import './public.css';
// The welcome screen (`/` and the password stage of `/login`) carries its own logo; public.css hides the header there.
export function PublicLayout(){const {session}=useSession();const signedIn=Boolean(session?.user_id);return <div className="dm public-app"><header className="opora-header"><Brand to={signedIn&&session?.is_staff?'/fund':'/'} subtitle="Благотворительный фонд «Дети Марии»"/>{signedIn&&<div className="public-account"><AccountControl/></div>}</header><main id="main-content"><Outlet/></main></div>;}
