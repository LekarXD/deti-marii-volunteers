// @vitest-environment jsdom
import React from 'react';
import {afterEach,beforeEach,describe,it,expect,vi} from 'vitest';
import {cleanup,render,screen,waitFor,within} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {MemoryRouter} from 'react-router-dom';
import {QueryClientProvider} from '@tanstack/react-query';
import {queryClient} from '../../api/queryClient';
import {keys} from '../../api/keys';
import {ApiError} from '../../api/transport';
import {GroupPage,nameLine} from './GroupPage';
const mocks=vi.hoisted(()=>({read:vi.fn(),prep:vi.fn(),hours:vi.fn()}));
vi.mock('./api',()=>({readAssignmentBriefing:mocks.read}));
vi.mock('../followups/api',()=>({readPreparation:mocks.prep}));
vi.mock('../followups/volunteerApi',async(importOriginal)=>({...await importOriginal<typeof import('../followups/volunteerApi')>(),useOwnHours:()=>({data:mocks.hours()})}));
const allowed={id:'allowed-person',display_name:'Разрешённый участник',birth_year:null,about:'Любит рисовать',communication:'Дайте время ответить',support:'Покажите первый шаг',interests:'Краски, Музыка',photo_asset_id:'private-photo',version:1,lifecycle:'active'};
const second={id:'second-person',display_name:'Катя',birth_year:2014,about:'Складывает оригами',communication:'Слушайте до конца',support:'Если шумно, отведите к окну',interests:'',photo_asset_id:null,version:1,lifecycle:'active'};
const prep={assignment_id:'assigned-event',title:'Арт-суббота',starts_at:'2028-01-03T11:00:00Z',ends_at:'2028-01-03T15:00:00Z',timezone:'Europe/Moscow',location:'загородная мастерская',contacts:[{display_name:'Юлия Смирнова',role:'Ведущий'},{display_name:'Алевтина Кузнецова',role:'Координатор'}]};
function page(search='?assignment_id=assigned-event'){return <MemoryRouter initialEntries={['/me/group'+search]}><QueryClientProvider client={queryClient}><GroupPage/></QueryClientProvider></MemoryRouter>;}
beforeEach(()=>{queryClient.clear();for(const mock of Object.values(mocks))mock.mockReset();mocks.prep.mockResolvedValue(prep);mocks.hours.mockReturnValue({confirmed_assignments:0,entries:[]});});
afterEach(()=>{cleanup();queryClient.clear();});
describe('assignment group briefing',()=>{
  it('loads the authorized group from the API and hides cached participant/photo after revocation',async()=>{
    const user=userEvent.setup();
    mocks.read.mockResolvedValue({assignment_id:'assigned-event',groups:[{id:'another-group',title:'Другая творческая группа'}],items:[allowed]});
    render(page());
    await screen.findByRole('heading',{name:'Другая творческая группа'});
    expect(mocks.read).toHaveBeenCalledWith('assigned-event',expect.any(AbortSignal));
    await user.click(screen.getByRole('button',{name:/Разрешённый/}));
    const dialog=screen.getByRole('dialog',{name:'Разрешённый'});
    expect(within(dialog).getByText('Покажите первый шаг')).toBeTruthy();
    expect(within(dialog).getByText('Краски')).toBeTruthy();expect(within(dialog).getByText('Музыка')).toBeTruthy();
    const images=screen.getAllByRole('img',{name:'Разрешённый'});
    expect(images[0].getAttribute('src')).toBe('/api/v1/me/assignments/assigned-event/participants/allowed-person/photo');
    expect(screen.queryByText('Для координатора')).toBeNull();
    mocks.read.mockRejectedValue(new ApiError(403,'assignment_inactive','Назначение отменено.'));
    await queryClient.invalidateQueries({queryKey:keys.all('assignment-group-briefing')});
    await screen.findByText('Назначение отменено.');
    await waitFor(()=>expect(screen.queryByText('Разрешённый')).toBeNull());
    expect(screen.queryByRole('img')).toBeNull();
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(screen.queryByText('Покажите первый шаг')).toBeNull();
  });
  it('shows the date, the leader and the team from the preparation contacts',async()=>{
    mocks.read.mockResolvedValue({assignment_id:'assigned-event',groups:[{id:'group',title:'Арт-суббота'}],items:[allowed,second]});
    render(page());
    expect(await screen.findByText('Пн, 3 января, 14:00, загородная мастерская')).toBeTruthy();
    expect(screen.getByRole('link',{name:'Написать ведущему'}).getAttribute('href')).toBe('/messages');
    expect(screen.getByRole('link',{name:'Первый выход'}).getAttribute('href')).toBe('/my/assignments/assigned-event/preparation');
    expect(screen.getByText(`Катя, ${Number(new Intl.DateTimeFormat('en-US',{year:'numeric',timeZone:'Europe/Moscow'}).format(new Date()))-2014}`)).toBeTruthy();
    expect(screen.getByText('Разрешённый')).toBeTruthy();
    expect(screen.getByRole('heading',{name:'Коллеги в команде'})).toBeTruthy();
    expect(screen.getByText('Алевтина')).toBeTruthy();expect(screen.getByText('Юлия')).toBeTruthy();expect(screen.getAllByRole('link',{name:'Написать'})).toHaveLength(2);
  });
  it('steps through the profiles and returns focus to the card on Escape',async()=>{
    const user=userEvent.setup();
    mocks.read.mockResolvedValue({assignment_id:'assigned-event',groups:[],items:[allowed,second]});
    render(page());
    const card=await screen.findByRole('button',{name:/Катя/});
    await user.click(card);
    expect(screen.getByRole('dialog',{name:/^Катя, \d+$/})).toBeTruthy();
    await waitFor(()=>expect(document.activeElement?.getAttribute('aria-label')).toBe('Закрыть'));
    await user.click(screen.getByRole('button',{name:'Следующий'}));
    expect(screen.getByRole('dialog',{name:'Разрешённый'})).toBeTruthy();
    await user.click(screen.getByRole('button',{name:'Предыдущий'}));
    expect(screen.getByRole('dialog',{name:/^Катя, \d+$/})).toBeTruthy();
    await user.keyboard('{Escape}');
    expect(screen.queryByRole('dialog')).toBeNull();
    await waitFor(()=>expect(document.activeElement).toBe(card));
  });
  it('closes the profile from the backdrop',async()=>{
    const user=userEvent.setup();
    mocks.read.mockResolvedValue({assignment_id:'assigned-event',groups:[],items:[second]});
    render(page());
    await user.click(await screen.findByRole('button',{name:/Катя/}));
    expect(screen.queryByRole('button',{name:'Следующий'})).toBeNull();
    await user.click(document.querySelector('.pf-back') as HTMLElement);
    expect(screen.queryByRole('dialog')).toBeNull();
  });
  it('shows a kid as «Саша, 14» from the birth year in Moscow and the name alone without it',()=>{
    expect(nameLine({display_name:'Саша',birth_year:2012},new Date('2026-10-22T12:00:00Z'))).toBe('Саша, 14');
    expect(nameLine({display_name:'[ДЕМО] Участник 1',birth_year:null})).toBe('Участник 1');
    expect(nameLine({display_name:'Саша Иванова',birth_year:null})).toBe('Саша');
    // 31 December 22:30 UTC is already the new year in Moscow.
    expect(nameLine({display_name:'Саша',birth_year:2012},new Date('2026-12-31T22:30:00Z'))).toBe('Саша, 15');
    expect(nameLine({display_name:'Лена',birth_year:null})).toBe('Лена');
  });
  it('requests no participant data until an assignment identifier is provided',()=>{
    render(page(''));
    expect(screen.getByRole('heading',{name:'Откройте памятку из своего назначения'})).toBeTruthy();
    expect(mocks.read).not.toHaveBeenCalled();
  });
});
