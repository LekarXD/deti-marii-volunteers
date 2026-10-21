import {expect,it,vi} from 'vitest';
vi.mock('./featureAvailability',()=>({enabledDestinations:new Set(['/home','/application','/onboarding','/opportunities','/my/assignments','/academy','/messages','/mentor','/simulator','/fund/notifications','/fund/simulator/review'])}));
import {candidateNavigation,coordinatorNavigation,getCandidateNavigation} from './navigation';
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
 expect(coordinatorNavigation.find(group=>group.label==='Ещё')?.links.map(link=>link.to)).toEqual(['/fund/notifications','/fund/simulator/review']);
});
