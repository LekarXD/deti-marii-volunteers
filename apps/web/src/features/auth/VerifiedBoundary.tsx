import {Navigate, Outlet, useLocation} from 'react-router-dom';
import {useSession} from '../../app/layouts';
import {verifiedEmail} from './AuthFields';

/** Only a server-authenticated identity may open the questionnaire. */
export function VerifiedBoundary() {
  const {session}=useSession();const location=useLocation();
  if(session?.mfa_required)return <Navigate to={`/login?next=${encodeURIComponent(location.pathname+location.search)}`} replace/>;
  return session?.user_id&&verifiedEmail(session)?<Outlet/>:<Navigate to="/register" replace/>;
}
