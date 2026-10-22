import {expect,it,vi} from 'vitest';
vi.mock('./featureAvailability',()=>({enabledDestinations:new Set(['/application','/onboarding','/opportunities','/my/assignments','/academy','/messages','/fund','/fund/responses','/fund/messages','/fund/schedule','/fund/scenarios','/fund/reports'])}));
import {candidateNavigation,candidatePrimaryNavigation,candidateMoreNavigation,coordinatorAccountLinks,coordinatorSectionOf,coordinatorSections,coordinatorShortcuts} from './navigation';
it('makes new learner destinations discoverable without six links crowding the desktop row',()=>{expect(candidateNavigation).toHaveLength(6);expect(candidatePrimaryNavigation.map(link=>link.to)).toEqual(['/application','/onboarding','/opportunities']);expect(candidateMoreNavigation.map(link=>link.label)).toEqual(['Мои занятия','Обучение','Сообщения']);});
it('keeps five sections without dropdowns, messages as an icon and rare pages in the profile menu',()=>{
 expect(coordinatorSections.map(section=>section.label)).toEqual(['Обзор','Мероприятия','Обучение']);
 expect(coordinatorShortcuts.map(item=>item.to)).toEqual(['/fund/messages']);
 expect(coordinatorAccountLinks.map(link=>link.to)).toEqual(['/fund/reports']);
});
it('lights the section on every tab page and never «Обзор» for a deeper path',()=>{
 expect(coordinatorSectionOf('/fund/responses')?.label).toBe('Мероприятия');
 expect(coordinatorSectionOf('/fund/events/7')?.label).toBe('Мероприятия');
 expect(coordinatorSectionOf('/fund/simulator/review')?.label).toBe('Обучение');
 expect(coordinatorSectionOf('/fund')?.label).toBe('Обзор');
 expect(coordinatorSectionOf('/fund/messages')?.label).toBe('Сообщения');
});
