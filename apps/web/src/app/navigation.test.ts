import {expect,it,vi} from 'vitest';
vi.mock('./featureAvailability',()=>({enabledDestinations:new Set(['/application','/fund','/fund/candidates','/fund/roles'])}));
import {candidateNavigation,coordinatorSections} from './navigation';
it('shows only integrated destinations and removes sections that have no routes',()=>{
 expect(candidateNavigation.map(link=>link.to)).toEqual(['/application']);
 expect(coordinatorSections.map(section=>section.label)).toEqual(['Обзор','Волонтёры','Мероприятия']);
 expect(coordinatorSections.map(section=>section.to)).toEqual(['/fund','/fund/candidates','/fund/roles']);
});
