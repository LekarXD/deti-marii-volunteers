import {useState, type FormEvent} from 'react';
import {Link, Navigate, useNavigate} from 'react-router-dom';
import type {components} from '../../api/generated/schema';
import {api} from '../../api/transport';
import {useSession} from '../../app/layouts';
import {Button, ErrorState, Field, Input} from '../../ui';
import {AuthFrame, OtpField, PasswordField, useResendCooldown, verifiedEmail, demoCodeAllowed} from './AuthFields';

type Challenge = components['schemas']['ChallengeView'];
export function RegisterPage() {
  const {session,refresh,logout}=useSession();
  const navigate=useNavigate();
  const [email,setEmail]=useState(''),[password,setPassword]=useState(''),[code,setCode]=useState('');
  const [challenge,setChallenge]=useState<Challenge|null>(null),[busy,setBusy]=useState(false),[error,setError]=useState<unknown>(null);
  const cooldown=useResendCooldown();
  const demo=demoCodeAllowed(challenge);
  if(session?.mfa_required)return <Navigate to="/login?next=%2Fapply" replace/>;
  if(session?.user_id&&verifiedEmail(session))return <Navigate to="/apply" replace/>;
  if(session?.user_id)return <AuthFrame title="Подтвердите почту" intro="Для анкеты нужен аккаунт с подтверждённой почтой."><p>В текущем аккаунте почта не подтверждена.</p>{error?<ErrorState error={error}/>:null}<Button loading={busy} onClick={async()=>{setBusy(true);try{await logout();}catch(value){setError(value);}finally{setBusy(false);}}}>Выйти и создать аккаунт</Button></AuthFrame>;
  async function requestCode(event?:FormEvent) {
    event?.preventDefault();setBusy(true);setError(null);
    try{const result=await api<Challenge>('/auth/register',{method:'POST',body:{email:email.trim(),password}});setChallenge(result);setCode('');cooldown.start();}
    catch(value){setError(value);}finally{setBusy(false);}
  }
  async function verify(event:FormEvent) {
    event.preventDefault();setBusy(true);setError(null);
    try{await api('/auth/register/verify',{method:'POST',body:{challenge_id:challenge!.challenge_id,code}});setPassword('');const current=await refresh();navigate(current.mfa_required?'/login?next=%2Fapply':'/apply',{replace:true});}
    catch(value){setError(value);}finally{setBusy(false);}
  }
  return <AuthFrame title={challenge?'Введите код':'Создать аккаунт'} intro="">
    {challenge ? <><p>{demo?email.trim():`Код из 6 цифр для ${email.trim()}.`}</p>{!demo&&challenge.delivery==='dev_inbox'&&<p className="auth-help">В тестовой установке письмо не отправляется. Код доступен администратору.</p>}<form className="auth-form" onSubmit={verify}><OtpField demo={demo} value={code} onChange={setCode} disabled={busy}/>{error?<ErrorState error={error}/>:null}<Button type="submit" loading={busy}>Подтвердить почту</Button><Button variant="ghost" disabled={busy||cooldown.remaining>0} onClick={()=>void requestCode()}>{cooldown.remaining>0?`Отправить код ещё раз через ${cooldown.remaining} с`:'Отправить код ещё раз'}</Button></form><button className="auth-text-button" disabled={busy} onClick={()=>{setChallenge(null);setCode('');setError(null);}}>Изменить почту</button></> : <><form className="auth-form" onSubmit={requestCode}><Field label="Электронная почта"><Input type="email" value={email} onChange={event=>setEmail(event.target.value)} autoComplete="email" placeholder="name@example.ru" maxLength={320} required autoFocus disabled={busy}/></Field><PasswordField fresh value={password} onChange={setPassword} disabled={busy}/>{error?<ErrorState error={error}/>:null}<Button type="submit" loading={busy}>Продолжить</Button></form><p className="auth-help">Уже есть аккаунт? <Link to="/login">Войти</Link></p></>}
  </AuthFrame>;
}
