// @vitest-environment jsdom
import React from 'react';
import {afterEach,beforeEach,expect,it,vi} from 'vitest';
import {cleanup,render,screen,within} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {MemoryRouter} from 'react-router-dom';
import {RolesPage} from './RolesPage';
import type {Role} from './api';
const mocks=vi.hoisted(()=>({command:vi.fn(),roles:vi.fn()}));
const role=(id:string,title:string,extra:Partial<Role>={})=>({id,title,task:`${title}: что делает`,direction:'',skills:[],preparation_defaults:[],approval_policy:'self_confirmation',archived_at:null,version:3,allowed_actions:[],volunteer_count:0,...extra}) as Role;
const active=[role('assist','Ассистент педагога',{direction:'Помощь на занятиях',skills:['Живопись и рисунок'],volunteer_count:14,preparation_defaults:[{key:'intro',title:'Курс «Знакомство с фондом»',level:'mandatory'}]}),role('fair','Волонтёр ярмарки',{direction:'Ярмарки',skills:['Продажи'],volunteer_count:1,preparation_defaults:[{key:'record',title:'Справка о несудимости',level:'recommended'}]}),role('photo','Предметный фотограф')];
const archived=[role('courier','Курьер',{archived_at:'2026-10-01T10:00:00Z'})];
vi.mock('./api',()=>({useRoles:(isArchived:boolean)=>{mocks.roles(isArchived);return {data:{pages:[{items:isArchived?archived:active}]},isPending:false,isError:false,hasNextPage:false}},useActivityCommand:()=>({mutateAsync:mocks.command,isPending:false,isError:false,reset:vi.fn()})}));
vi.mock('./eventsApi',()=>({useMatchingOptions:()=>({data:{directions:['Творчество','Помощь на занятиях','Ярмарки'],skills:['Живопись и рисунок','Продажи','Фотография']}})}));
afterEach(cleanup);beforeEach(()=>{mocks.command.mockReset().mockResolvedValue({});mocks.roles.mockClear();});
const mount=(path='/fund/roles')=>render(<MemoryRouter initialEntries={[path]}><RolesPage/></MemoryRouter>);

it('lists roles as one list with their volunteers and section tabs as the title',()=>{mount();
 expect(screen.getByRole('heading',{level:1,name:'Роли'})).toBeTruthy();expect(screen.getByRole('link',{name:'Расписание'}).getAttribute('href')).toBe('/fund/schedule');
 expect(screen.getByRole('button',{name:'Новая роль'}).className).toContain('btn-secondary');expect(document.querySelectorAll('.btn-primary')).toHaveLength(0);
 const assist=screen.getByRole('button',{name:/Ассистент педагога/});expect(assist.getAttribute('aria-expanded')).toBe('false');expect(within(assist).getByText('14 волонтёров')).toBeTruthy();
 expect(within(screen.getByRole('button',{name:/Волонтёр ярмарки/})).getByText('1 волонтёр')).toBeTruthy();expect(within(screen.getByRole('button',{name:/Предметный фотограф/})).getByText('пока никого')).toBeTruthy();
 expect(document.querySelectorAll('.role-row')).toHaveLength(3);expect(screen.queryByText(/Согласование/)).toBeNull();expect(document.body.textContent).not.toContain('·');});

it('searches by title or skill and switches to the archive',async()=>{const user=userEvent.setup();mount();
 await user.type(screen.getByRole('searchbox',{name:'Найти роль'}),'продаж');expect(screen.getByRole('button',{name:/Волонтёр ярмарки/})).toBeTruthy();expect(screen.queryByRole('button',{name:/Ассистент педагога/})).toBeNull();
 await user.clear(screen.getByRole('searchbox',{name:'Найти роль'}));await user.type(screen.getByRole('searchbox',{name:'Найти роль'}),'нет такой');expect(screen.getByText('Ролей не нашли')).toBeTruthy();
 await user.clear(screen.getByRole('searchbox',{name:'Найти роль'}));await user.click(screen.getByRole('radio',{name:'Архив'}));expect(mocks.roles).toHaveBeenLastCalledWith(true);expect(screen.getByRole('button',{name:/Курьер/})).toBeTruthy();
 await user.click(screen.getByRole('button',{name:/Курьер/}));await user.click(screen.getByRole('button',{name:'Вернуть из архива'}));expect(mocks.command).toHaveBeenCalledWith(expect.objectContaining({path:'/coord/roles/courier/restore',body:{expected_version:3}}));expect(screen.getByRole('status').textContent).toBe('Роль вернули из архива');},20000);

it('opens a role in place, saves its form and keeps the stored approval rule',async()=>{const user=userEvent.setup();mount();
 await user.click(screen.getByRole('button',{name:/Волонтёр ярмарки/}));expect(screen.getByRole('button',{name:/Волонтёр ярмарки/}).getAttribute('aria-expanded')).toBe('true');
 expect((screen.getByLabelText('Название') as HTMLInputElement).value).toBe('Волонтёр ярмарки');expect(screen.getByRole('radio',{name:'Ярмарки'}).getAttribute('aria-checked')).toBe('true');expect(screen.getByRole('button',{name:'Продажи'}).getAttribute('aria-pressed')).toBe('true');
 const prep=screen.getByRole('group',{name:'До первого выхода'});expect((within(prep).getByLabelText('Справка о несудимости') as HTMLInputElement).checked).toBe(true);expect((within(prep).getByLabelText('Курс «Знакомство с фондом»') as HTMLInputElement).checked).toBe(false);
 await user.click(within(prep).getByLabelText('Курс «Знакомство с фондом»'));await user.type(within(prep).getByLabelText('Свой пункт подготовки'),'Медкнижка{Enter}');await user.click(screen.getByRole('radio',{name:'Творчество'}));await user.click(screen.getByRole('button',{name:'Фотография'}));
 await user.clear(screen.getByLabelText('Название'));await user.type(screen.getByLabelText('Название'),'Продавец на ярмарке');expect(screen.getAllByRole('button',{name:'Сохранить'})).toHaveLength(1);await user.click(screen.getByRole('button',{name:'Сохранить'}));
 const call=mocks.command.mock.calls[0][0];expect(call).toMatchObject({path:'/coord/roles/fair',method:'PATCH',body:{title:'Продавец на ярмарке',direction:'Творчество',skills:['Продажи','Фотография'],approval_policy:'self_confirmation',expected_version:3}});
 expect(call.body.preparation_defaults.map((item:{title:string})=>item.title)).toEqual(['Справка о несудимости','Курс «Знакомство с фондом»','Медкнижка']);expect(call.body.preparation_defaults[2].level).toBe('recommended');
 expect(screen.getByRole('status').textContent).toBe('Роль «Продавец на ярмарке» сохранена');expect(screen.queryByLabelText('Название')).toBeNull();},20000);

it('adds a new role as an open row on top, needs a title and never sends an approval rule',async()=>{const user=userEvent.setup();mount('/fund/roles?archive=1');
 await user.click(screen.getByRole('button',{name:'Новая роль'}));expect(mocks.roles).toHaveBeenLastCalledWith(false);const first=document.querySelector('.role-item');expect(first?.classList.contains('is-open')).toBe(true);expect(within(first as HTMLElement).getByText('Опишите, что делает волонтёр')).toBeTruthy();
 expect(document.activeElement).toBe(screen.getByLabelText('Название'));expect(screen.queryByRole('button',{name:'В архив'})).toBeNull();
 await user.click(screen.getByRole('button',{name:'Сохранить'}));expect(mocks.command).not.toHaveBeenCalled();expect(screen.getByText('Введите название роли')).toBeTruthy();
 await user.type(screen.getByLabelText('Название'),'Водитель');await user.type(screen.getByLabelText('Что делает волонтёр'),'Отвозит ребят на выезды');await user.click(screen.getByRole('button',{name:'Сохранить'}));
 expect(mocks.command).toHaveBeenCalledWith(expect.objectContaining({path:'/coord/roles',method:'POST',body:{title:'Водитель',task:'Отвозит ребят на выезды',direction:'',skills:[],preparation_defaults:[]}}));
 await user.click(screen.getByRole('button',{name:'Новая роль'}));await user.click(screen.getByRole('button',{name:'Отмена'}));expect(document.querySelector('.role-item.is-open')).toBeNull();expect(screen.queryByText('Опишите, что делает волонтёр')).toBeNull();},20000);

it('archives an open role from its form',async()=>{const user=userEvent.setup();mount();
 await user.click(screen.getByRole('button',{name:/Предметный фотограф/}));await user.click(screen.getByRole('button',{name:'В архив'}));
 expect(mocks.command).toHaveBeenCalledWith(expect.objectContaining({path:'/coord/roles/photo/archive',body:{expected_version:3}}));expect(screen.getByRole('status').textContent).toBe('Роль убрана в архив');},20000);
