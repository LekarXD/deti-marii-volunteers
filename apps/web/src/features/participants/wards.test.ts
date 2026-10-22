import {describe,expect,it} from 'vitest';
import {ageLabel,initials,wardLine} from './wards';
import {namesLine} from './ParticipantPage';

describe('ward helpers',()=>{
 it('builds initials from letters only and skips bracketed labels',()=>{
  expect(initials('Миша Котов')).toBe('МК');
  expect(initials('[ДЕМО] Иван Петров')).toBe('ИП');
  expect(initials('[ДЕМО] «Аня» Смирнова-Орлова')).toBe('АС');
  expect(initials('анна')).toBe('А');
  expect(initials('[ДЕМО]')).toBe('Д');
  expect(initials('— 123')).toBe('?');
 });
 it('shows the age with the right Russian plural and hides implausible years',()=>{
  expect(ageLabel(2014,2026)).toBe('12 лет');
  expect(ageLabel(2025,2026)).toBe('1 год');
  expect(ageLabel(2004,2026)).toBe('22 года');
  expect(ageLabel(2015,2026)).toBe('11 лет');
  expect(ageLabel(2005,2026)).toBe('21 год');
  expect(ageLabel(1914,2026)).toBe('112 лет');
  expect(ageLabel(2026,2026)).toBe('');
  expect(ageLabel(null,2026)).toBe('');
  expect(wardLine(null,[{id:'g',title:'«Подсолнухи»',membership_id:'m',valid_from:'2026-01-01'}])).toBe('«Подсолнухи»');
 });
 it('joins volunteer names without a middle dot',()=>{
  expect(namesLine(['Анна'])).toBe('Анна');
  expect(namesLine(['Анна','Тимур'])).toBe('Анна и Тимур');
  expect(namesLine(['Анна','Тимур','Полина'])).toBe('Анна, Тимур и Полина');
 });
});
