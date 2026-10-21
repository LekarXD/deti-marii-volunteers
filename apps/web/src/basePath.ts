import {normalizeAppBasePath,withAppBase,withoutAppBase} from '../base-path';
export const getAppBasePath=()=>normalizeAppBasePath(import.meta.env.VITE_APP_BASE_PATH??import.meta.env.BASE_URL);
export const appPath=(path:string)=>withAppBase(path,getAppBasePath());
export const appRoute=(path:string)=>withoutAppBase(path,getAppBasePath());
/** Keep provider, blob and data URLs intact; qualify only app-local root paths. */
export const appResourceUrl=(url:string)=>url.startsWith('/')?appPath(url):url;
export function apiPath(path:string){withAppBase(path,'');const route=appRoute(path);return appPath(route==='/api/v1'||route.startsWith('/api/v1/')?route:`/api/v1${route}`);}
