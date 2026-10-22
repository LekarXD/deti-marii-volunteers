import {useState} from 'react';
import {Link} from 'react-router-dom';
import {useMutation} from '@tanstack/react-query';
import {api,ApiError} from '../../api/transport';
import {useSession} from '../../app/layouts';
import type {components} from '../../api/generated/schema';
import {Button,Field,Input} from '../../ui';
import {useProfileCommand} from './api';
type Challenge=components['schemas']['ContactChangeChallengeView'];
const failureText=(error:unknown)=>error instanceof Error&&error.message?error.message:'Не получилось. Попробуй ещё раз.';
const deliveryLabel=(state:string)=>state==='dev_inbox'?'Запрос создан. В этой среде подтверждение доступно в локальном ящике проверки.':state==='pending'?'Запрос создан, письмо ожидает отправки. Когда оно придёт, введи код.':state==='unavailable'?'Отправка писем сейчас недоступна. Повтори позже.':state==='failed'?'Письмо не отправлено. Повтори запрос.':state==='unknown'?'Пока неясно, ушло ли письмо. Проверь почту, прежде чем просить снова.':'Мы отправили письмо на новую почту. Открой его и введи код.';

/** Changing the sign-in email: a bound challenge proves the new address, then the rotated session is refreshed. */
export function ContactChangePanel(){
 const [email,setEmail]=useState(''),[token,setToken]=useState(''),[challenge,setChallenge]=useState<Challenge|null>(null),{refresh}=useSession();
 const request=useProfileCommand<Challenge>('/auth/contact-change');
 const verify=useMutation({mutationFn:()=>api<components['schemas']['AuthSessionView']>('/auth/contact-change/verify',{method:'POST',body:{challenge_id:challenge?.challenge_id,token:token.trim()}}),onSuccess:async()=>{await refresh();}});
 const stepUp=(request.error instanceof ApiError&&request.error.code==='step_up_required')||(verify.error instanceof ApiError&&verify.error.code==='step_up_required');
 return <div className="prof-contact-change">
  <Field label="Новая почта"><Input type="email" autoComplete="email" value={email} onChange={e=>setEmail(e.target.value)} disabled={request.isPending||verify.isPending}/></Field>
  <div className="row wrap"><Button variant="secondary" disabled={!email.trim()||request.isPending||verify.isPending} onClick={()=>void request.mutateAsync({email}).then(setChallenge).catch(()=>{})}>{challenge?'Запросить подтверждение снова':'Подтвердить новую почту'}</Button>{stepUp&&<Link className="btn btn-ghost" to="/login?next=/profile">Войти снова для смены почты</Link>}</div>
  {request.error&&<p className="err" role="alert">{failureText(request.error)}</p>}
  {challenge&&<>
   <p className="p" role="status">{deliveryLabel(challenge.delivery_state)}</p>
   <Field label="Код подтверждения из письма" hint={`Код действует до ${new Date(challenge.expires_at).toLocaleTimeString('ru',{hour:'2-digit',minute:'2-digit'})}`}><Input value={token} onChange={e=>setToken(e.target.value)} autoComplete="one-time-code"/></Field>
   <div className="row"><Button disabled={!token.trim()||verify.isPending} onClick={()=>verify.mutate()}>Сохранить подтверждённую почту</Button></div>
   {verify.error&&<p className="err" role="alert">{failureText(verify.error)}</p>}
  </>}
 </div>;
}
