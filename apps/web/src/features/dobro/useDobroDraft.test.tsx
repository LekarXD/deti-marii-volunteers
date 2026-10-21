// @vitest-environment jsdom
import {act,renderHook} from '@testing-library/react';
import {describe,it,expect} from 'vitest';
import {useDobroDraft} from './useDobroDraft';
describe('Dobro editors preserve changes during background refetch',()=>{
 it('keeps a dirty profile after conflict until an explicit resolution',()=>{
  const initial={version:1,profile_url:'https://dobro.ru/volunteers/1'};
  const {result,rerender}=renderHook(({server})=>useDobroDraft(server),{initialProps:{server:initial}});
  act(()=>result.current.setDraft({...initial,profile_url:'https://dobro.ru/volunteers/2'}));
  rerender({server:{version:2,profile_url:'https://dobro.ru/volunteers/3'}});
  expect(result.current.conflict).toBe(true);
  expect(result.current.draft.profile_url).toBe('https://dobro.ru/volunteers/2');
  act(()=>result.current.keepMine());
  expect(result.current.conflict).toBe(false);
  expect(result.current.draft).toEqual({version:2,profile_url:'https://dobro.ru/volunteers/2'});
 });
 it('updates an untouched editor and reconciles a successful save',()=>{
  const {result,rerender}=renderHook(({server})=>useDobroDraft(server),{initialProps:{server:{version:1,title:'Первое'}}});
  rerender({server:{version:2,title:'На сервере'}});
  expect(result.current.draft.title).toBe('На сервере');
  act(()=>result.current.setDraft({version:2,title:'Мой текст'}));
  rerender({server:{version:3,title:'Мой текст'}});
  expect(result.current.dirty).toBe(false);
  expect(result.current.draft.version).toBe(3);
 });
});
