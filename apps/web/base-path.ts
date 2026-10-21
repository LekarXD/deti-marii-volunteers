/** Public mount only: never a URL, origin, query, encoded separator or dot segment. */
export function normalizeAppBasePath(value:string|undefined):string {
 if(value===undefined||value===''||value==='/')return '';
 if(!/^\/[A-Za-z0-9_-]+(?:\/[A-Za-z0-9_-]+)*\/?$/.test(value))throw new Error('Invalid VITE_APP_BASE_PATH');
 return value.replace(/\/$/,'');
}
export function withAppBase(path:string,base:string):string {
 if(!path.startsWith('/')||path.startsWith('//')||/[\\\u0000-\u0020\u007f]/.test(path))throw new Error('Application path must be same-origin');
 const pathname=path.split(/[?#]/,1)[0];
 let decoded:string;try{decoded=decodeURIComponent(pathname);}catch{throw new Error('Invalid application path');}
 if(/%(?:2f|5c)/i.test(pathname)||/[\\\u0000-\u001f\u007f]/.test(decoded)||decoded.split('/').some(part=>part==='.'||part==='..'))throw new Error('Invalid application path');
 const prefix=normalizeAppBasePath(base);
 return prefix&&(path===prefix||path.startsWith(`${prefix}/`)||path.startsWith(`${prefix}?`)||path.startsWith(`${prefix}#`))?path:`${prefix}${path}`;
}
export function withoutAppBase(path:string,base:string):string {
 const prefix=normalizeAppBasePath(base);
 return prefix&&(path===prefix||path.startsWith(`${prefix}/`)||path.startsWith(`${prefix}?`)||path.startsWith(`${prefix}#`))?(path.slice(prefix.length)||'/'):path;
}
