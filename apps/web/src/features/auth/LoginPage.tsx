import {appRoute} from '../../basePath';
import {useEffect, useState, type FormEvent} from 'react';
import {useNavigate, useSearchParams} from 'react-router-dom';
import {api} from '../../api/transport';
import type {components} from '../../api/generated/schema';
import {useSession} from '../../app/layouts';
import {Button, Card, Field, Input, Segmented} from '../../ui';
import './auth.css';
import {FormError} from './AuthFields';
import {WelcomePage} from './WelcomePage';

type AuthSession = components['schemas']['AuthSessionView'];
type Challenge = components['schemas']['ChallengeView'];
type MfaSession = components['schemas']['MfaSessionView'];

/** Only relative application paths can become a return destination. */
export function safeReturnPath(value: string | null, fallback = '/application'): string {
  if (!value || !value.startsWith('/') || value.startsWith('//') || /[\\\u0000-\u0020\u007f]/.test(value)) return fallback;
  try {
    const parsed = new URL(appRoute(value), 'https://opora.invalid');
    const pathname=decodeURIComponent(parsed.pathname).replace(/\/+$/,'')||'/';
    if (parsed.origin !== 'https://opora.invalid' || ['/login','/register','/forgot-password'].includes(pathname) || pathname==='/api' || pathname.startsWith('/api/')) return fallback;
    // Reject encoded delimiters as well: server/proxy normalization must not change origin.
    if (/%(?:2f|5c|00|0a|0d)/i.test(value)) return fallback;
    return `${parsed.pathname}${parsed.search}${parsed.hash}`;
  } catch { return fallback; }
}

interface LinkProof {challengeId: string; token: string;}
function readLink(params: URLSearchParams): LinkProof | null {
  const challengeId=params.get('challenge_id')??'', token=params.get('token')??'';
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(challengeId) && token.length>=20 && token.length<=200 ? {challengeId,token} : null;
}

export function LoginPage() {
  const {session}=useSession();
  const [params]=useSearchParams();
  // Link proof is kept in memory only. A GET never verifies or consumes the challenge.
  const [link,setLink]=useState(()=>readLink(params));
  const next=safeReturnPath(params.get('next'),session?.is_staff || Boolean(session && 'mfa_required' in session && session.mfa_required)?'/fund':'/');
  const navigate=useNavigate();
  useEffect(()=>{
    if (!params.has('token') && !params.has('challenge_id')) return;
    const clean=new URLSearchParams();if(params.get('next'))clean.set('next',next);
    navigate({pathname:'/login',search:clean.size?`?${clean}`:''},{replace:true});
  },[params,next,navigate]);
  // Session refresh can replace the principal. A fresh form derives its next stage from
  // the actual server session; no in-flight local stage survives that identity change.
  const principalKey=`${session?.foundation_id}:${session?.user_id??session?.registration_id}:${Boolean(session && 'mfa_required' in session && session.mfa_required)}`;
  return <AuthForm key={principalKey} link={link} legacy={params.get('legacy')==='1'} next={next} onProofConsumed={()=>setLink(null)}/>;
}

function AuthForm({link,next,legacy,onProofConsumed}:{link:LinkProof|null;next:string;legacy:boolean;onProofConsumed:()=>void}) {
  const {session,refresh,logout}=useSession();
  const navigate=useNavigate();
  const [email,setEmail]=useState(''),[challenge,setChallenge]=useState<Challenge|null>(null),[proof,setProof]=useState<LinkProof|null>(link),[token,setToken]=useState(''),[code,setCode]=useState(''),[method,setMethod]=useState('totp'),[busy,setBusy]=useState(false),[error,setError]=useState<unknown>(null);
  const mfaRequired=Boolean(session && 'mfa_required' in session && session.mfa_required);
  const signedIn=Boolean(session?.user_id && !mfaRequired);
  async function requestChallenge(event:FormEvent) {
    event.preventDefault();setBusy(true);setError(null);
    try {const value=await api<Challenge>('/auth/challenges',{method:'POST',body:{email:email.trim(),purpose:'login'}});setChallenge(value);setProof(null);setToken('');}
    catch(e){setError(e);}finally{setBusy(false);}
  }
  async function verify(event:FormEvent) {
    event.preventDefault();setBusy(true);setError(null);
    const payload=proof?{challenge_id:proof.challengeId,token:proof.token}:{challenge_id:challenge?.challenge_id,token:token.trim()};
    try {await api<AuthSession>('/auth/challenges/verify',{method:'POST',body:payload});onProofConsumed();setProof(null);setToken('');const current=await refresh();if(!('mfa_required' in current && current.mfa_required))navigate(next,{replace:true});}
    catch(e){setError(e);}finally{setBusy(false);}
  }
  async function verifyMfa(event:FormEvent) {
    event.preventDefault();setBusy(true);setError(null);
    try {await api<MfaSession>('/auth/mfa/verify',{method:'POST',body:{code:code.trim()}});setCode('');await refresh();navigate(next,{replace:true});}
    catch(e){setCode('');setError(e);}finally{setBusy(false);}
  }
  async function signOut() {setBusy(true);setError(null);try{await logout();}catch(e){setError(e);}finally{setBusy(false);}}
  // The password stage is the same screen as the anonymous entry page.
  if(!mfaRequired && !signedIn && !proof && !challenge && !legacy) return <WelcomePage next={next} autoFocus onSignedIn={current=>{if(!current.mfa_required)navigate(next,{replace:true});}}/>;
  return <div className="auth-page"><Card className="auth-card">{mfaRequired ? <><h1 className="h1">Подтвердите вход</h1><p>Почта подтверждена. Для доступа к работе фонда нужен второй шаг.</p><Segmented label="Способ подтверждения" value={method} onChange={value=>{setMethod(value);setCode('');setError(null);}} options={[{value:'totp',label:'Приложение'},{value:'recovery',label:'Код восстановления'}]}/><form onSubmit={verifyMfa} className="auth-form"><Field label={method==='totp'?'Код из приложения':'Одноразовый код восстановления'} hint={method==='totp'?'Введите текущий шестизначный код из вашего приложения для входа.':'Используйте один из кодов, сохранённых при настройке защиты.'}><Input value={code} onChange={e=>setCode(e.target.value)} type={method==='totp'?'text':'password'} inputMode={method==='totp'?'numeric':'text'} autoComplete="one-time-code" minLength={6} maxLength={100} pattern={method==='totp'?'[0-9]{6}':undefined} required autoFocus disabled={busy}/></Field>{error ? <FormError error={error}/> : null}<Button type="submit" loading={busy}>Подтвердить вход</Button></form><p className="auth-help">Если доступа к приложению и кодам нет, обратитесь к администратору фонда.</p><Button variant="ghost" loading={busy} onClick={()=>void signOut()}>Выйти из аккаунта</Button></> : signedIn && !proof ? <><h1 className="h1">Вы вошли в аккаунт</h1><p>Можно продолжить работу в личном кабинете.</p>{error ? <FormError error={error}/> : null}<div className="auth-actions"><Button onClick={()=>navigate(next,{replace:true})}>Продолжить</Button><Button variant="ghost" loading={busy} onClick={()=>void signOut()}>Войти с другой почтой</Button></div></> : proof || challenge ? <><h1 className="h1">{proof?'Подтвердите вход по ссылке':'Подтвердите почту'}</h1>{proof ? <p>Нажмите кнопку, чтобы подтвердить вход в этом браузере.</p> : <><p role="status">Запрос на вход поставлен в очередь.</p><p className="auth-help">{challenge?.delivery==='dev_inbox'?'В тестовой установке письмо не отправляется. Получите ссылку для входа у администратора.':'Письмо ожидает отправки. Когда оно придёт, откройте ссылку или вставьте код подтверждения ниже.'}</p></>}<form onSubmit={verify} className="auth-form">{!proof && <Field label="Код подтверждения из письма"><Input type="password" value={token} onChange={e=>setToken(e.target.value)} autoComplete="one-time-code" minLength={20} maxLength={200} required disabled={busy}/></Field>}{error ? <FormError error={error}/> : null}<Button type="submit" loading={busy}>{proof?'Подтвердить вход':'Войти'}</Button><Button variant="ghost" disabled={busy} onClick={()=>{setChallenge(null);setProof(null);onProofConsumed();setToken('');setError(null);}}>Указать другую почту</Button></form></> : <><h1 className="h1">Вход по почте</h1><p>Мы подготовим ссылку для входа. Пароль не нужен.</p><form onSubmit={requestChallenge} className="auth-form"><Field label="Электронная почта"><Input type="email" value={email} onChange={e=>setEmail(e.target.value)} placeholder="name@example.ru" autoComplete="email" required maxLength={320} autoFocus disabled={busy}/></Field>{error ? <FormError error={error}/> : null}<Button type="submit" loading={busy}>Получить ссылку для входа</Button></form><p className="auth-help">Вход сотрудника дополнительно защищён кодом из приложения.</p></>}</Card></div>;
}
