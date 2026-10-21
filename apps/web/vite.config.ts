import {defineConfig,loadEnv} from 'vite';
import react from '@vitejs/plugin-react';
import {normalizeAppBasePath,withAppBase,withoutAppBase} from './base-path';
export default defineConfig(({mode})=>{
 const env=loadEnv(mode,process.cwd(),''),mount=normalizeAppBasePath(env.VITE_APP_BASE_PATH??process.env.VITE_APP_BASE_PATH);
 const target={target:env.OPORA_DEV_API_ORIGIN??process.env.OPORA_DEV_API_ORIGIN??'http://127.0.0.1:8001',changeOrigin:false,rewrite:(path:string)=>withoutAppBase(path,mount)};
 return {base:mount?`${mount}/`:'/',plugins:[react()],build:{rollupOptions:{input:{app:new URL('./index.html',import.meta.url).pathname,recorder:new URL('./recorder.html',import.meta.url).pathname}}},server:{proxy:{[withAppBase('/api',mount)]:target,[withAppBase('/version.json',mount)]:target}}};
});
