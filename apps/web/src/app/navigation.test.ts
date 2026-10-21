import {expect,it,vi} from 'vitest';
vi.mock('./featureAvailability',()=>({enabledDestinations:new Set(['/application','/fund','/fund/candidates','/fund/roles'])}));
import {candidateNavigation,coordinatorNavigation} from './navigation';
it('shows only integrated destinations and removes groups that have no routes',()=>{
 expect(candidateNavigation.map(link=>link.to)).toEqual(['/application']);
 expect(coordinatorNavigation.map(group=>group.label)).toEqual(['Волонтёры','Занятия']);
 expect(coordinatorNavigation.flatMap(group=>group.links).map(link=>link.to)).toEqual(['/fund/candidates','/fund/roles']);
});
