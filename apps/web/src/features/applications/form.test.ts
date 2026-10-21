import {describe,expect,it} from 'vitest';
import {masked,visible,displayDate} from './form';
describe('version four candidate form controls',()=>{
  it('formats phone and birth date without a native date popup or age policy',()=>{
    expect(masked('89991234567','phone')).toBe('+7 (999) 123-45-67');
    expect(masked('01012012','date')).toBe('01.01.2012');
    expect(displayDate('2012-01-01')).toBe('01.01.2012');
  });
  it('shows only selected direction skill groups and conditional experience',()=>{
    expect(visible({field:'directions',value:['Творчество','Ярмарки']},{directions:['Как специалист']})).toBe(false);
    expect(visible({field:'directions',value:['Творчество','Ярмарки']},{directions:['Ярмарки']})).toBe(true);
    expect(visible({field:'volExp',value:'Да'},{volExp:'Нет'})).toBe(false);
    expect(visible({field:'volExp',value:'Да'},{volExp:'Да'})).toBe(true);
  });
  it('keeps name/telegram entry consistent with source masks',()=>{
    expect(masked('анна-мария иванова','name')).toBe('Анна-Мария Иванова');
    expect(masked('@@anna user','telegram')).toBe('@annauser');
  });
});
