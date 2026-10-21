import {useEffect, useState, type ReactNode} from 'react';
import {Card, Field, Icon, Input} from '../../ui';
import type {Session} from '../../api/transport';
import './auth.css';

export const verifiedEmail = (session: Session | null): string | null => (session as (Session & {verified_email?: string | null}) | null)?.verified_email ?? null;
export const demoCodeAllowed = (challenge: ({challenge_id:string;demo_code_allowed?:boolean}) | null): boolean => Boolean(challenge?.demo_code_allowed);

export function AuthFrame({title, intro, children}: {title: string; intro: string; children: ReactNode}) {
  return <div className="auth-page"><div className="auth-intro"><p className="eyebrow">Опора · Дети Марии</p><h1 className="h1">{title}</h1><p className="lead">{intro}</p></div><Card className="auth-card">{children}</Card></div>;
}

export function PasswordField({value, onChange, disabled, fresh = false}: {value: string; onChange: (value: string) => void; disabled?: boolean; fresh?: boolean}) {
  const [shown, setShown] = useState(false);
  return <Field label={fresh ? 'Придумайте пароль' : 'Пароль'} hint={fresh ? 'От 12 до 128 символов' : undefined}><div className="auth-password"><Input value={value} onChange={event=>onChange(event.target.value)} type={shown ? 'text' : 'password'} autoComplete={fresh ? 'new-password' : 'current-password'} minLength={fresh ? 12 : 1} maxLength={128} required disabled={disabled}/><button type="button" aria-label={shown ? 'Скрыть пароль' : 'Показать пароль'} aria-pressed={shown} onClick={()=>setShown(current=>!current)} disabled={disabled}><Icon name="eye"/></button></div></Field>;
}

export function OtpField({value, onChange, disabled, demo=false}: {value: string; onChange: (value: string) => void; disabled?: boolean; demo?: boolean}) {
  return <Field label={demo?'Код подтверждения':'Код из письма'} hint={demo?'Для демоверсии подойдёт любой код':undefined}><Input className={demo?undefined:'auth-otp'} value={value} onChange={event=>onChange(demo?event.target.value.slice(0,128):event.target.value.replace(/[^0-9]/g, '').slice(0, 6))} type="text" inputMode={demo?'text':'numeric'} autoComplete="one-time-code" pattern={demo?'.*\\S.*':'[0-9]{6}'} minLength={demo?1:6} maxLength={demo?128:6} required autoFocus disabled={disabled}/></Field>;
}

export function useResendCooldown() {
  const [remaining, setRemaining] = useState(0);
  useEffect(()=>{if(remaining<=0)return;const timer=window.setTimeout(()=>setRemaining(value=>Math.max(0,value-1)),1000);return()=>window.clearTimeout(timer);},[remaining]);
  return {remaining, start:()=>setRemaining(60)};
}
