import {afterEach,it,expect,vi} from 'vitest';
import {normalizeAppBasePath,withAppBase} from '../base-path';
import {apiPath,appPath,appResourceUrl,appRoute} from './basePath';
afterEach(()=>vi.unstubAllEnvs());
it('accepts a root or strict origin-local mount and rejects ambiguous deployment configuration',()=>{
 expect(normalizeAppBasePath(undefined)).toBe('');expect(normalizeAppBasePath('/')).toBe('');expect(normalizeAppBasePath('/deti-marii/')).toBe('/deti-marii');
 for(const value of ['deti-marii','//other','https://other.test/app','/app//nested','/app/../other','/app%2fother','/app?x=1','/app#x','/app name'])expect(()=>normalizeAppBasePath(value)).toThrow();
});
it.each(['/','/deti-marii'])('qualifies app resources and API paths exactly once at %s',mount=>{
 vi.stubEnv('VITE_APP_BASE_PATH',mount);const prefix=mount==='/'?'':mount;
 expect(appPath('/')).toBe(`${prefix}/`);expect(apiPath('/me/profile')).toBe(`${prefix}/api/v1/me/profile`);expect(apiPath('/api/v1/me/profile')).toBe(`${prefix}/api/v1/me/profile`);expect(apiPath(`${prefix}/api/v1/me/profile`)).toBe(`${prefix}/api/v1/me/profile`);
 expect(appResourceUrl('/api/v1/assets/id/content')).toBe(`${prefix}/api/v1/assets/id/content`);expect(appResourceUrl('blob:https://example.invalid/id')).toBe('blob:https://example.invalid/id');expect(appResourceUrl('https://provider.invalid/signed?token=x')).toBe('https://provider.invalid/signed?token=x');expect(appRoute(`${prefix}/fund?x=1`)).toBe('/fund?x=1');
});
it('never lets root-relative resource normalization escape the configured application',()=>{
 for(const path of ['//other.test/x','/../other','/%2e%2e/other','/a/../../other','/a%2fb','/a\\b','https://other.test/x'])expect(()=>withAppBase(path,'/deti-marii')).toThrow();
});
