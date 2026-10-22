import {useState, type FormEvent} from 'react';
import {Link} from 'react-router-dom';
import fundLogo from '../../assets/fund/marias-children-logo.svg';
import welcomeArt from '../../assets/fund/welcome-art.webp';
import {ApiError} from '../../api/errors';
import {api, type Session} from '../../api/transport';
import type {components} from '../../api/generated/schema';
import {useSession} from '../../app/layouts';
import {Button, Card, Field, Icon, Input} from '../../ui';
import './auth.css';
import {FormError, PasswordField} from './AuthFields';

type AuthSession = components['schemas']['AuthSessionView'];

/** Sign in right here, or start the volunteer application. Shown on `/` and as the password stage of `/login`. */
export function WelcomePage({next,autoFocus=false,onSignedIn}:{next?:string;autoFocus?:boolean;onSignedIn?:(session:Session)=>void}) {
  return <div className="welcome"><Card className="welcome-login"><img className="welcome-logo" src={fundLogo} alt="Дети Марии" width="162" height="32"/><section className="welcome-login-body" aria-labelledby="welcome-title"><h1 id="welcome-title" className="h1">Вход в кабинет</h1><p className="auth-description">Для волонтёров и команды фонда</p><PasswordLoginForm next={next} autoFocus={autoFocus} onSignedIn={onSignedIn}/></section><p className="welcome-foot">Благотворительный фонд «Дети Марии» · <a href="https://mariaschildren.ru">mariaschildren.ru</a></p></Card><aside className="welcome-art" aria-labelledby="welcome-new-title"><img src={welcomeArt} alt=""/><div className="welcome-invite"><h2 id="welcome-new-title">Впервые у нас?</h2><p>Заполните анкету — координатор свяжется с вами и пригласит на собеседование.</p><Link className="btn btn-lg welcome-invite-action" to="/register">Стать волонтёром<Icon name="arrow-right"/></Link></div></aside></div>;
}

/** Password sign-in. A rejected password is a field error. */
function PasswordLoginForm({next,autoFocus,onSignedIn}:{next?:string;autoFocus:boolean;onSignedIn?:(session:Session)=>void}) {
  const {refresh}=useSession();
  const [email,setEmail]=useState(''),[password,setPassword]=useState(''),[busy,setBusy]=useState(false),[error,setError]=useState<unknown>(null);
  const rejected=error instanceof ApiError && error.code==='invalid_credentials';
  async function login(event:FormEvent) {
    event.preventDefault();setBusy(true);setError(null);
    try{await api<AuthSession>('/auth/login',{method:'POST',body:{email:email.trim(),password},retainSessionOnUnauthorized:true});console.log('[dbg] login ok, refreshing');setPassword('');const s=await refresh();console.log('[dbg] refreshed',s.user_id);onSignedIn?.(s);}
    catch(value){console.log('[dbg] login catch',value);setError(value);}finally{setBusy(false);}
  }
  return <form className="auth-form" onSubmit={login}><Field label="Электронная почта"><Input type="email" value={email} onChange={event=>{setEmail(event.target.value);setError(null);}} aria-invalid={rejected||undefined} autoComplete="email" maxLength={320} placeholder="name@example.ru" required autoFocus={autoFocus} disabled={busy}/></Field><PasswordField value={password} onChange={value=>{setPassword(value);setError(null);}} disabled={busy} error={rejected?'Неверная почта или пароль':undefined}/><Link className="auth-forgot" to={next?`/forgot-password?next=${encodeURIComponent(next)}`:'/forgot-password'}>Забыли пароль?</Link>{error&&!rejected?<FormError error={error}/>:null}<Button type="submit" loading={busy}>Войти</Button></form>;
}
