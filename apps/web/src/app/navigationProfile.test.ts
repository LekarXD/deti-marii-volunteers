import {expect,it,vi} from 'vitest';
vi.mock('./featureAvailability',()=>({enabledDestinations:new Set(['/home','/application','/onboarding','/opportunities','/my/assignments','/academy','/messages','/mentor','/simulator','/fund/notifications','/fund/simulator/review'])}));
import {candidateNavigation,coordinatorAccountLinks,coordinatorSections,getCandidateNavigation,volunteerNavigation,volunteerSectionFor,volunteerSections} from './navigation';
it('swaps the registration cabinet entry for Home only for verified users, keeping three desktop links',()=>{
 const verified=getCandidateNavigation(true),registration=getCandidateNavigation(false);
 expect(verified.primary.map(link=>link.to)).toEqual(['/home','/onboarding','/opportunities']);
 expect(registration.primary.map(link=>link.to)).toEqual(['/application','/onboarding','/opportunities']);
 expect(registration.items.some(link=>link.to==='/home')).toBe(false);
 expect(verified.primary.length).toBe(3);
});
it('puts enabled mentor/simulator under More and hides webinars until its route is integrated',()=>{
 expect(getCandidateNavigation(true).more.map(link=>link.to)).toEqual(['/my/assignments','/academy','/messages','/mentor','/simulator']);
 expect(candidateNavigation.some(link=>link.to==='/webinars')).toBe(false);
 expect(coordinatorAccountLinks.map(link=>link.to)).toEqual(['/fund/notifications']);
 expect(coordinatorSections.find(section=>section.label==='Обучение')?.to).toBe('/fund/simulator/review');
});

it('groups verified volunteer destinations by the current prototype without inventing a detail context',()=>{expect(volunteerNavigation.map(group=>group.label)).toEqual(['Возможности','Академия','Ещё']);expect(volunteerNavigation.flatMap(group=>group.links).some(link=>link.to==='/me/group')).toBe(false);expect(volunteerNavigation.find(group=>group.label==='Возможности')?.links.map(link=>link.to)).toEqual(['/opportunities']);});

it('gives volunteers plain enabled sections and keeps a section current on its sub-pages',()=>{
 // The mocked availability enables /home, /academy, /messages, /mentor, /simulator but not /my/schedule or /hours.
 expect(volunteerSections.map(section=>section.label)).toEqual(['Главная','Обучение','Сообщения']);
 expect(volunteerSectionFor('/academy/lessons/7')?.label).toBe('Обучение');
 expect(volunteerSectionFor('/mentor')?.label).toBe('Обучение');
 expect(volunteerSectionFor('/messages')?.label).toBe('Сообщения');
 expect(volunteerSectionFor('/events/42')).toBeUndefined();
});
