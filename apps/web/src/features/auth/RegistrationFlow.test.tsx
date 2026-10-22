// @vitest-environment jsdom
import {afterEach,beforeEach,describe,it,expect,vi} from 'vitest';
import {cleanup,render,screen} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {MemoryRouter,Route,Routes} from 'react-router-dom';
import {RegisterPage} from './RegisterPage';
import {ResetPasswordPage} from './ResetPasswordPage';
import {VerifiedBoundary} from './VerifiedBoundary';
import {WelcomePage} from './WelcomePage';

const state=vi.hoisted(()=>({session:{user_id:null,mfa_required:false,verified_email:null} as {user_id:string|null;mfa_required:boolean;verified_email:string|null;demo_email_codes?:boolean},api:vi.fn(),refresh:vi.fn()}));
vi.mock('../../api/transport',()=>({api:state.api}));
vi.mock('../../app/layouts',()=>({useSession:()=>({session:state.session,refresh:state.refresh})}));
afterEach(cleanup);
beforeEach(()=>{state.api.mockReset();state.refresh.mockReset();state.session={user_id:null,mfa_required:false,verified_email:null};});
const challenge={challenge_id:'challenge-1',status:'queued',delivery:'pending'};
function page(path='/register') {return <MemoryRouter initialEntries={[path]}><Routes><Route path="/" element={<WelcomePage/>}/><Route path="/register" element={<RegisterPage/>}/><Route path="/forgot-password" element={<ResetPasswordPage/>}/><Route path="/login" element={<h1>Вход</h1>}/><Route element={<VerifiedBoundary/>}><Route path="/apply" element={<h1>Анкета</h1>}/></Route></Routes></MemoryRouter>;}

describe('welcome and questionnaire boundaries',()=>{
 it('signs in on the entry page and offers the questionnaire to newcomers',()=>{render(page('/'));expect(screen.getByRole('heading',{name:'Вход в кабинет'})).toBeTruthy();expect(screen.getByLabelText('Электронная почта')).toBeTruthy();expect(screen.getByLabelText('Пароль')).toBeTruthy();expect(screen.getByRole('button',{name:'Войти'})).toBeTruthy();expect(screen.getByRole('link',{name:'Стать волонтёром'}).getAttribute('href')).toBe('/register');expect(screen.getByRole('link',{name:'Забыли пароль?'}).getAttribute('href')).toBe('/forgot-password');});
 it('redirects an anonymous direct questionnaire URL to registration',()=>{render(page('/apply'));expect(screen.getByRole('heading',{name:'Создать аккаунт'})).toBeTruthy();expect(screen.queryByRole('heading',{name:'Анкета'})).toBeNull();});
 it('keeps an authenticated staff principal behind MFA',()=>{state.session={user_id:'staff',mfa_required:true,verified_email:'staff@example.ru'};render(page('/apply'));expect(screen.getByRole('heading',{name:'Вход'})).toBeTruthy();expect(screen.queryByRole('heading',{name:'Анкета'})).toBeNull();});
 it('keeps an unverified identity out without a redirect loop',()=>{state.session={user_id:'unverified',mfa_required:false,verified_email:null};render(page('/apply'));expect(screen.getByRole('heading',{name:'Подтвердите почту'})).toBeTruthy();expect(screen.queryByRole('heading',{name:'Анкета'})).toBeNull();});
 it('retains verified access after remounting the page',()=>{state.session={user_id:'verified-volunteer',mfa_required:false,verified_email:'person@example.ru'};const view=render(page('/apply'));expect(screen.getByRole('heading',{name:'Анкета'})).toBeTruthy();view.unmount();render(page('/apply'));expect(screen.getByRole('heading',{name:'Анкета'})).toBeTruthy();});
});

it('registers, accepts a pasted six-digit code with a leading zero and opens the questionnaire only after verification',async()=>{
 const user=userEvent.setup();state.api.mockResolvedValueOnce(challenge).mockResolvedValueOnce({});state.refresh.mockImplementation(async()=>{state.session={user_id:'new-volunteer',mfa_required:false,verified_email:'new@example.ru'};return state.session;});
 render(page());await user.type(screen.getByLabelText('Электронная почта'),'new@example.ru');await user.type(screen.getByLabelText('Придумайте пароль'),'long-new-password');
 expect(screen.getByLabelText('Придумайте пароль').getAttribute('autocomplete')).toBe('new-password');
 await user.click(screen.getByRole('button',{name:'Продолжить'}));expect(await screen.findByRole('heading',{name:'Введите код'})).toBeTruthy();
 expect(screen.queryByRole('heading',{name:'Анкета'})).toBeNull();expect(state.refresh).not.toHaveBeenCalled();
 expect(screen.getByRole('button',{name:/Отправить код ещё раз через/}).hasAttribute('disabled')).toBe(true);
 const code=screen.getByLabelText('Код из письма');await user.click(code);await user.paste('012345');expect((code as HTMLInputElement).value).toBe('012345');
 await user.click(screen.getByRole('button',{name:'Подтвердить почту'}));await screen.findByRole('heading',{name:'Анкета'});
 expect(state.api).toHaveBeenNthCalledWith(1,'/auth/register',{method:'POST',body:{email:'new@example.ru',password:'long-new-password'}});
 expect(state.api).toHaveBeenNthCalledWith(2,'/auth/register/verify',{method:'POST',body:{challenge_id:'challenge-1',code:'012345'}});
});

it('keeps a rejected OTP at verification and supports retry',async()=>{
 const user=userEvent.setup();state.api.mockResolvedValueOnce(challenge).mockRejectedValueOnce(new Error('Код не подошёл'));
 render(page());await user.type(screen.getByLabelText('Электронная почта'),'new@example.ru');await user.type(screen.getByLabelText('Придумайте пароль'),'long-new-password');await user.click(screen.getByRole('button',{name:'Продолжить'}));await user.type(await screen.findByLabelText('Код из письма'),'123456');await user.click(screen.getByRole('button',{name:'Подтвердить почту'}));
 expect(await screen.findByText('Код не подошёл')).toBeTruthy();expect(screen.getByLabelText('Код из письма')).toBeTruthy();expect(state.refresh).not.toHaveBeenCalled();
});

it('recovers a password with a generic account response and preserves staff MFA',async()=>{
 const user=userEvent.setup();state.api.mockResolvedValueOnce(challenge).mockResolvedValueOnce({});state.refresh.mockResolvedValue({user_id:'staff',mfa_required:true});
 render(page('/forgot-password?next=%2Fapply'));await user.type(screen.getByLabelText('Электронная почта'),'staff@example.ru');await user.click(screen.getByRole('button',{name:'Получить код'}));
 expect((await screen.findByRole('status')).textContent).toContain('Если аккаунт с адресом staff@example.ru существует');
 await user.type(screen.getByLabelText('Код из письма'),'001234');await user.type(screen.getByLabelText('Придумайте пароль'),'a-new-long-password');await user.click(screen.getByRole('button',{name:'Сохранить пароль и войти'}));await screen.findByRole('heading',{name:'Вход'});
 expect(state.api).toHaveBeenLastCalledWith('/auth/password/reset/verify',{method:'POST',body:{challenge_id:'challenge-1',code:'001234',password:'a-new-long-password'}});
});

it('accepts any nonempty demo code only when this server challenge enables demo codes',async()=>{
 const user=userEvent.setup();state.api.mockResolvedValueOnce({...challenge,demo_code_allowed:true}).mockResolvedValueOnce({});state.refresh.mockImplementation(async()=>{state.session={user_id:'demo-user',mfa_required:false,verified_email:'demo@example.ru',demo_email_codes:true};return state.session;});
 render(page());await user.type(screen.getByLabelText('Электронная почта'),'demo@example.ru');await user.type(screen.getByLabelText('Придумайте пароль'),'demo-long-password');await user.click(screen.getByRole('button',{name:'Продолжить'}));
 const code=await screen.findByLabelText('Код подтверждения');expect(screen.getByText('Для демоверсии подойдёт любой код')).toBeTruthy();expect(screen.queryByText(/письмо не отправляется/)).toBeNull();expect(screen.queryByLabelText('Код из письма')).toBeNull();
 await user.type(code,'любой');await user.click(screen.getByRole('button',{name:'Подтвердить почту'}));await screen.findByRole('heading',{name:'Анкета'});
 expect(state.api).toHaveBeenLastCalledWith('/auth/register/verify',{method:'POST',body:{challenge_id:'challenge-1',code:'любой'}});
});

it('keeps real account recovery six-digit even when the session belongs to a demo installation',async()=>{
 const user=userEvent.setup();state.session.demo_email_codes=true;state.api.mockResolvedValueOnce({...challenge,demo_code_allowed:false});
 render(page('/forgot-password'));await user.type(screen.getByLabelText('Электронная почта'),'real@example.ru');await user.click(screen.getByRole('button',{name:'Получить код'}));
 const code=await screen.findByLabelText('Код из письма');expect(code.getAttribute('pattern')).toBe('[0-9]{6}');expect(screen.queryByText('Для демоверсии подойдёт любой код')).toBeNull();
});
