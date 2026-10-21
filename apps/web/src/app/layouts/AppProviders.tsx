import {createContext,useContext,useEffect,useState,type ReactNode} from 'react';
import {QueryClientProvider} from '@tanstack/react-query';
import {queryClient} from '../../api/queryClient';
import {getSession,initializeSession,onSessionChange,clearSession,api,type Session} from '../../api/transport';
import {ErrorBoundary,ErrorState,LoadingState,ToastProvider} from '../../ui';
import '../../../../../packages/design-tokens/tokens.css';
import './layouts.css';
import {installChunkRecovery} from '../../ui/chunkRecovery';
const SessionContext=createContext<{session:Session|null;refresh:()=>Promise<Session>;logout:()=>Promise<void>}>({session:null,refresh:()=>initializeSession(true),logout:async()=>{}});
export const useSession=()=>useContext(SessionContext);
function SessionProvider({children}:{children:ReactNode}){const [session,setSession]=useState(getSession);const [error,setError]=useState<unknown>(null);const [attempt,setAttempt]=useState(0);
 useEffect(()=>{let alive=true;const unsub=onSessionChange(()=>{if(alive){const current=getSession();setSession(current);if(!current)setAttempt(n=>n+1);}});initializeSession().then(value=>{if(alive){setSession(value);setError(null);}}).catch(value=>{if(alive)setError(value);});return()=>{alive=false;unsub();};},[attempt]);
 const refresh=async()=>{const value=await initializeSession(true);setSession(value);return value;};
 const logout=async()=>{await api('/auth/logout',{method:'POST'});clearSession();setAttempt(n=>n+1);};
 return <SessionContext.Provider value={{session,refresh,logout}}>{error?<div className="dm shell"><ErrorState error={error} retry={()=>{setError(null);setAttempt(n=>n+1);}}/></div>:!session?<div className="dm shell"><LoadingState label="Открываем Опору…"/></div>:children}</SessionContext.Provider>;
}
export function AppProviders({children}:{children:ReactNode}){useEffect(()=>installChunkRecovery(),[]);return <QueryClientProvider client={queryClient}><ToastProvider><ErrorBoundary><SessionProvider>{children}</SessionProvider></ErrorBoundary></ToastProvider></QueryClientProvider>;}
