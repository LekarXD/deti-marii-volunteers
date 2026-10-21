// Browser-only demo data. No uploads or messages are sent to external services.
const demoRead = (key, fallback) => {try {const raw = sessionStorage.getItem('opora-prototype-v1:'+key);return raw ? JSON.parse(raw) : fallback;} catch (_) {return fallback;}};
const demoWrite = (key, value) => {try {sessionStorage.setItem('opora-prototype-v1:'+key,JSON.stringify(value));} catch (_) {}};
