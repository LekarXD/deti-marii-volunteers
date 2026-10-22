import {Fragment,createContext,useCallback,useContext,useEffect,useRef,useState,type ReactNode} from 'react';
import {QueryClientProvider} from '@tanstack/react-query';
import {queryClient} from '../../api/queryClient';
import {getSession,initializeSession,onSessionChange,clearSession,api,type Session} from '../../api/transport';
import {ErrorBoundary,ErrorState,LoadingState,ToastProvider,useToast} from '../../ui';
import '../../../../../packages/design-tokens/tokens.css';
import './layouts.css';
import {installChunkRecovery} from '../../ui/chunkRecovery';
const SessionContext=createContext<{session:Session|null;ended:boolean;settle:()=>void;refresh:()=>Promise<Session>;logout:()=>Promise<void>}>({session:null,ended:false,settle:()=>{},refresh:()=>initializeSession(true),logout:async()=>{}});
export const useSession=()=>useContext(SessionContext);
function SessionProvider({children}:{children:ReactNode}){const [session,setSession]=useState(getSession);const [error,setError]=useState<unknown>(null);const [attempt,setAttempt]=useState(0);const [ended,setEnded]=useState(false);const {toast}=useToast();
 const user=useRef(getSession()?.user_id??null),leaving=useRef(false);
 // A signed-in session that turns anonymous without «Выйти» here has expired or was revoked (password reset, logout in another tab).
 const accept=useCallback((value:Session)=>{if(user.current&&!value.user_id&&!leaving.current){setEnded(true);toast('Сессия завершилась. Войдите снова.');}else if(value.user_id)setEnded(false);user.current=value.user_id??null;leaving.current=false;setSession(value);},[toast]);
 const settle=useCallback(()=>setEnded(false),[]);
 useEffect(()=>{let alive=true;const unsub=onSessionChange(()=>{if(alive){const current=getSession();setSession(current);if(!current)setAttempt(n=>n+1);}});initializeSession().then(value=>{if(alive){accept(value);setError(null);}}).catch(value=>{if(alive)setError(value);});return()=>{alive=false;unsub();};},[attempt,accept]);
 const refresh=async()=>{const value=await initializeSession(true);accept(value);return value;};
 const logout=async()=>{await api('/auth/logout',{method:'POST'});leaving.current=true;clearSession();setAttempt(n=>n+1);};
 return <SessionContext.Provider value={{session,ended,settle,refresh,logout}}>{error?<div className="dm shell"><ErrorState error={error} retry={()=>{setError(null);setAttempt(n=>n+1);}}/></div>:!session?<div className="dm shell"><LoadingState label="Открываем Опору…"/></div>:<Fragment key={`${session.foundation_id}:${session.user_id??session.registration_id??'anonymous'}`}>{children}</Fragment>}</SessionContext.Provider>;
}
export function AppProviders({children}:{children:ReactNode}){useEffect(()=>installChunkRecovery(),[]);return <QueryClientProvider client={queryClient}><ToastProvider><ErrorBoundary><SessionProvider>{children}</SessionProvider></ErrorBoundary></ToastProvider></QueryClientProvider>;}
