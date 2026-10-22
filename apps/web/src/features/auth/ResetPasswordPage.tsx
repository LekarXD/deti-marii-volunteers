import {useState, type FormEvent} from 'react';
import {Link, useNavigate, useSearchParams} from 'react-router-dom';
import type {components} from '../../api/generated/schema';
import {api} from '../../api/transport';
import {useSession} from '../../app/layouts';
import {Button, Field, Input} from '../../ui';
import {AuthFrame, FormError, OtpField, PasswordField, useResendCooldown, demoCodeAllowed} from './AuthFields';
import {safeReturnPath} from './LoginPage';

type Challenge = components['schemas']['ChallengeView'];
export function ResetPasswordPage() {
  const {refresh}=useSession();const navigate=useNavigate();const [params]=useSearchParams();
  const next=safeReturnPath(params.get('next'),'/');
  const [email,setEmail]=useState(''),[code,setCode]=useState(''),[password,setPassword]=useState('');
  const [challenge,setChallenge]=useState<Challenge|null>(null),[busy,setBusy]=useState(false),[error,setError]=useState<unknown>(null);
  const cooldown=useResendCooldown();
  const demo=demoCodeAllowed(challenge);
  async function requestCode(event?:FormEvent) {
    event?.preventDefault();setBusy(true);setError(null);
    try{const result=await api<Challenge>('/auth/password/reset',{method:'POST',body:{email:email.trim()}});setChallenge(result);setCode('');cooldown.start();}catch(value){setError(value);}finally{setBusy(false);}
  }
  async function reset(event:FormEvent) {
    event.preventDefault();setBusy(true);setError(null);
    try{await api('/auth/password/reset/verify',{method:'POST',body:{challenge_id:challenge!.challenge_id,code,password}});setPassword('');const current=await refresh();navigate(current.mfa_required?`/login?next=${encodeURIComponent(next)}`:next,{replace:true});}catch(value){setError(value);}finally{setBusy(false);}
  }
  return <AuthFrame title={challenge?'Новый пароль':'Восстановить пароль'} intro="">
    {challenge&&<p role="status">{demo?'Введите любой код и задайте новый пароль.':`Если аккаунт с адресом ${email.trim()} существует, вы получите код для восстановления.`}</p>}
    <form className="auth-form" onSubmit={challenge?reset:requestCode}>{challenge?<><OtpField demo={demo} value={code} onChange={setCode} disabled={busy}/><PasswordField fresh value={password} onChange={setPassword} disabled={busy}/></>:<Field label="Электронная почта"><Input type="email" value={email} onChange={event=>setEmail(event.target.value)} autoComplete="email" maxLength={320} placeholder="name@example.ru" required autoFocus disabled={busy}/></Field>}{error?<FormError error={error}/>:null}<Button type="submit" loading={busy}>{challenge?'Сохранить пароль и войти':'Получить код'}</Button>{challenge&&<Button variant="ghost" disabled={busy||cooldown.remaining>0} onClick={()=>void requestCode()}>{cooldown.remaining>0?`Отправить код ещё раз через ${cooldown.remaining} с`:'Отправить код ещё раз'}</Button>}</form><p className="auth-help"><Link to={`/login?next=${encodeURIComponent(next)}`}>Вернуться ко входу</Link></p>
  </AuthFrame>;
}
