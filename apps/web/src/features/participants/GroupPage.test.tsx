// @vitest-environment jsdom
import React from 'react';
import {afterEach,beforeEach,describe,it,expect,vi} from 'vitest';
import {cleanup,render,screen,waitFor} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {MemoryRouter} from 'react-router-dom';
import {QueryClientProvider} from '@tanstack/react-query';
import {queryClient} from '../../api/queryClient';
import {keys} from '../../api/keys';
import {ApiError} from '../../api/transport';
import {GroupPage} from './GroupPage';
const mocks=vi.hoisted(()=>({read:vi.fn()}));
vi.mock('./api',()=>({readAssignmentBriefing:mocks.read}));
function page(search='?assignment_id=assigned-event'){return <MemoryRouter initialEntries={['/me/group'+search]}><QueryClientProvider client={queryClient}><GroupPage/></QueryClientProvider></MemoryRouter>;}
beforeEach(()=>{queryClient.clear();mocks.read.mockReset();});
afterEach(()=>{cleanup();queryClient.clear();});
describe('assignment group briefing',()=>{
  it('loads the authorized group from the API and hides cached participant/photo after revocation',async()=>{
    const user=userEvent.setup();
    mocks.read.mockResolvedValue({assignment_id:'assigned-event',groups:[{id:'another-group',title:'Другая творческая группа'}],items:[{id:'allowed-person',display_name:'Разрешённый участник',birth_year:null,about:'Любит рисовать',communication:'Дайте время ответить',support:'Покажите первый шаг',interests:'Краски',photo_asset_id:'private-photo',version:1,lifecycle:'active'}]});
    render(page());
    await screen.findByRole('heading',{name:'Другая творческая группа'});
    expect(mocks.read).toHaveBeenCalledWith('assigned-event',expect.any(AbortSignal));
    await user.click(screen.getByRole('button',{name:/Разрешённый участник/}));
    expect(screen.getByText('Покажите первый шаг')).toBeTruthy();
    const images=screen.getAllByRole('img',{name:'Разрешённый участник'});
    expect(images[0].getAttribute('src')).toBe('/api/v1/me/assignments/assigned-event/participants/allowed-person/photo');
    expect(screen.queryByText('Для координатора')).toBeNull();
    mocks.read.mockRejectedValue(new ApiError(403,'assignment_inactive','Назначение отменено.'));
    await queryClient.invalidateQueries({queryKey:keys.all('assignment-group-briefing')});
    await screen.findByText('Назначение отменено.');
    await waitFor(()=>expect(screen.queryByText('Разрешённый участник')).toBeNull());
    expect(screen.queryByRole('img')).toBeNull();
    expect(screen.queryByText('Покажите первый шаг')).toBeNull();
  });
  it('requests no participant data until an assignment identifier is provided',()=>{
    render(page(''));
    expect(screen.getByRole('heading',{name:'Откройте памятку из своего назначения'})).toBeTruthy();
    expect(mocks.read).not.toHaveBeenCalled();
  });
});
