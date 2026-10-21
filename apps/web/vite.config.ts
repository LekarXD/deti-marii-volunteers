import {defineConfig} from 'vite';
import react from '@vitejs/plugin-react';
export default defineConfig({plugins:[react()],build:{rollupOptions:{input:{app:new URL('./index.html',import.meta.url).pathname,recorder:new URL('./recorder.html',import.meta.url).pathname}}},server:{proxy:{'/api':{target:'http://127.0.0.1:8001',changeOrigin:false},'/version.json':{target:'http://127.0.0.1:8001',changeOrigin:false}}}});
