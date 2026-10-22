// @vitest-environment jsdom
import type {ReactNode} from 'react';
import {afterEach,beforeEach,expect,it,vi} from 'vitest';
import {cleanup,render,screen,within} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {QueryClient,QueryClientProvider} from '@tanstack/react-query';
import {MemoryRouter} from 'react-router-dom';
import * as transport from '../../api/transport';
import {ApiError} from '../../api/errors';
import type {components} from '../../api/generated/schema';
import {AssignmentCard} from './Participation';
import type {AssignmentParticipation} from './participationApi';
const mutateAsync=vi.fn(async()=>({}));
vi.mock('../../app/layouts/AppProviders',()=>({useSession:()=>({session:{user_id:'volunteer',permissions:[]}})}));
vi.mock('./api',()=>({useActivityCommand:()=>({mutateAsync,isPending:false,isError:false})}));
let event:components['schemas']['VolunteerEventDetail']|null;
beforeEach(()=>{
 event=null;
 vi.spyOn(transport,'api').mockImplementation(async <T,>(path:string):Promise<T>=>{
  if(path==='/me/events/event'&&event)return event as T;
  throw new ApiError(404,'occurrence_not_found','Занятие не найдено.');
 });
});
afterEach(()=>{cleanup();mutateAsync.mockClear();vi.restoreAllMocks();});
const item=(changes:Partial<AssignmentParticipation>={}):AssignmentParticipation=>({id:'invite',user_id:'volunteer',display_name:'Тестовый волонтёр',occurrence_id:'event',staffing_need_id:'need',occurrence_status:'scheduled',title:'Подготовка ярмарки',role_title:'Помощь на ярмарке',status:'invited',origin:'invitation',approved_at:null,confirmed_at:null,starts_at:'2099-10-25T11:00:00Z',ends_at:'2099-10-25T13:00:00Z',timezone:'Europe/Moscow',location:'Мастерская',readiness:[],history:[],allowed_actions:['confirm','decline'],conditions_version:1,points_multiplier:1.5,approval_required:true,version:1,...changes});
const steps=()=>Array.from(document.querySelectorAll('.tl')).map(node=>`${node.querySelector('b')!.textContent}:${node.className.replace('tl','').trim()}`);
function show(node:ReactNode){const client=new QueryClient({defaultOptions:{queries:{retry:false}}});return render(<QueryClientProvider client={client}><MemoryRouter>{node}</MemoryRouter></QueryClientProvider>);}

it('lets the volunteer answer a coordinator invitation even when the role needs approval',()=>{
 show(<AssignmentCard item={item()}/>);
 expect(screen.getByText('Тебя приглашают')).toBeTruthy();
 expect(screen.queryByText('Ждёт ответа координатора')).toBeNull();
 expect(screen.getByRole('button',{name:'Я приду'})).toBeTruthy();
 expect(screen.getByRole('button',{name:'Не смогу'})).toBeTruthy();
 expect(screen.getByText('Баллы ×1,5')).toBeTruthy();
 expect(steps()).toEqual(['Приглашение:done','Твоё подтверждение:now','Занятие:','Часы:']);
 expect(document.body.textContent).not.toMatch(/Координатор согласовал участие\. Подтверди|ещё не согласовал/);
});

it('shows an own request and a freed reserve place as waiting for the coordinator',async()=>{
 show(<AssignmentCard item={item({origin:'self',version:3})}/>);
 expect(screen.getByText('Ждёт ответа координатора')).toBeTruthy();
 expect(screen.queryByRole('button',{name:'Я приду'})).toBeNull();
 expect(steps()).toEqual(['Заявка:done','Согласование координатора:now','Занятие:','Часы:']);
 await userEvent.setup().click(screen.getByRole('button',{name:'Отменить заявку'}));
 expect(mutateAsync).toHaveBeenCalledWith(expect.objectContaining({path:'/assignments/invite/decline',body:{expected_version:3}}));
 cleanup();
 show(<AssignmentCard item={item({origin:'reserve'})}/>);
 expect(screen.getByText('Освободилось место из резерва')).toBeTruthy();
 expect(screen.getByText('Координатор подтвердит участие.')).toBeTruthy();
 expect(screen.getByRole('button',{name:'Не смогу'})).toBeTruthy();
 expect(screen.queryByText('Место за тобой')).toBeNull();
 expect(steps()).toEqual(['Место из резерва:done','Согласование координатора:now','Занятие:','Часы:']);
});

it('asks why before declining and then says a replacement is being found',async()=>{
 show(<AssignmentCard item={item({version:4})}/>);
 const user=userEvent.setup();
 await user.click(screen.getByRole('button',{name:'Не смогу'}));
 const send=screen.getByRole('button',{name:'Сообщить координатору'});
 expect(send.getAttribute('aria-disabled')).toBe('true');
 await user.click(within(screen.getByRole('radiogroup',{name:'Почему не получится'})).getByRole('radio',{name:'Болезнь'}));
 await user.click(send);
 expect(mutateAsync).toHaveBeenCalledWith(expect.objectContaining({path:'/assignments/invite/decline',body:{expected_version:4,reason:'Не смогу прийти: болезнь'}}));
 expect(await screen.findByText('Ищем замену')).toBeTruthy();
 expect(screen.queryByRole('button',{name:'Всё-таки приду'})).toBeNull();
});

it('lays a confirmed занятие out like the event page: role, dates, audience, team and the way to the group',async()=>{
 event={occurrence_id:'event',series_id:'s',title:'Подготовка ярмарки',program:'Ярмарки',kind:'activity',format:'onsite',location:'Мастерская',audience:'Гости ярмарки и ребята из «Радуги»',status:'scheduled',
  starts_at:'2099-10-25T11:00:00Z',ends_at:'2099-10-25T13:00:00Z',timezone:'Europe/Moscow',best_need_id:'need',reasons:[],full:false,conflict:false,algorithm_version:'rules-v3',can_sign_up:true,
  needs:[{id:'need',version:1,role_id:'r',role_title:'Помощь на ярмарке',task:'Оформить стол и встретить гостей',required:4,confirmed:3,missing:1,approval_policy:'self_confirmation',preparation_requirements:[],allowed_actions:[],points_multiplier:1.5}],
  other_dates:[{occurrence_id:'later',starts_at:'2099-11-01T11:00:00Z',ends_at:'2099-11-01T13:00:00Z',full:false,mine:false}],contacts:[{role:'Ведущий',display_name:'[ДЕМО] Елена Петрова'}]};
 show(<AssignmentCard item={item({status:'confirmed',approved_at:'2026-10-22T10:00:00Z',confirmed_at:'2026-10-22T11:00:00Z',allowed_actions:['cancel'],readiness:[{key:'intro',title:'Знакомство с фондом',level:'mandatory',state:'fulfilled'}]})}/>);
 expect(screen.getByText('Место за тобой')).toBeTruthy();
 expect(screen.getByText('До 16:00, Мастерская')).toBeTruthy();
 expect((screen.getByText('Место за тобой').closest('.card-hero') as HTMLElement).style.background).toMatch(/tint/);
 expect(screen.getByRole('link',{name:'Подготовиться'}).getAttribute('href')).toBe('/my/assignments/invite/preparation');
 expect(screen.getByRole('button',{name:'Не смогу'})).toBeTruthy();
 expect(screen.getByRole('link',{name:'Кто будет в группе'}).getAttribute('href')).toBe('/me/group?assignment_id=invite');
 expect(screen.getByRole('img',{name:'Готово'})).toBeTruthy();
 const role=screen.getByRole('heading',{name:'Чем помочь'}).closest('section') as HTMLElement;
 expect(within(role).getByText('Помощь на ярмарке')).toBeTruthy();
 expect(within(role).getByText('Баллы ×1,5')).toBeTruthy();
 expect(await within(role).findByText('Оформить стол и встретить гостей')).toBeTruthy();
 expect(within(role).getByText('Осталось одно место')).toBeTruthy();
 expect(screen.getByRole('link',{name:'Вс, 1 ноября'}).getAttribute('href')).toBe('/events/later');
 expect(screen.getByText('Гости ярмарки и ребята из «Радуги»')).toBeTruthy();
 const team=screen.getByRole('heading',{name:'Команда'}).closest('.card') as HTMLElement;
 expect(within(team).getByText('Елена, ведущий')).toBeTruthy();
 expect(steps()).toEqual(['Приглашение:done','Твоё подтверждение:done','Занятие:now','Часы:']);
});

it('keeps the full staff card for coordinators',()=>{
 show(<AssignmentCard staff item={item()}/>);
 expect(screen.getByText('Тестовый волонтёр, Помощь на ярмарке')).toBeTruthy();
 expect(screen.getByText('История участия')).toBeTruthy();
});
