// @vitest-environment jsdom
import React from 'react';
import {afterEach,it,expect,vi} from 'vitest';
import {cleanup,render,screen} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {RoomErrors} from './RoomErrors';
import {ApiError} from '../../../api/errors';
afterEach(cleanup);
it('shows a room command and its caught presentation only once and keeps manual retry',async()=>{
 const message='Медиасервер не поддерживает необходимое подтверждение доступа.',retry=vi.fn();
 render(<RoomErrors errors={[message,null,undefined,new ApiError(503,'rtc_revocation_unsupported',message)]} retry={retry}/>);
 expect(screen.getAllByRole('alert')).toHaveLength(1);expect(screen.getAllByText(message)).toHaveLength(1);await userEvent.setup().click(screen.getByRole('button',{name:'Попробовать ещё раз'}));expect(retry).toHaveBeenCalledOnce();
});
it('retains independent action, media and material failures instead of hiding them behind the first one',()=>{
 render(<RoomErrors errors={['Не удалось открыть комнату.','Связь прервалась.','Не удалось загрузить слайд.',new Error('Не удалось открыть комнату.')]} retry={vi.fn()}/>);
 expect(screen.getAllByRole('alert')).toHaveLength(3);expect(screen.getByText('Связь прервалась.')).toBeTruthy();expect(screen.getByText('Не удалось загрузить слайд.')).toBeTruthy();expect(screen.getAllByRole('button',{name:'Попробовать ещё раз'})).toHaveLength(3);
});
