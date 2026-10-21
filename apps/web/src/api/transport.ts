import {apiPath} from '../basePath';
/** Cookie transport adapted from OD client.js principal pinning/retry mechanics.
 * Server remains the authority for Origin, CSRF, permissions and receipts. */
import type {components} from './generated/schema';
export type Session = components['schemas']['AuthSessionView'];
import {ApiError,readApiError} from './errors';
export {ApiError} from './errors';
export interface ApiOptions extends Omit<RequestInit, 'body' | 'credentials'> {
  body?: unknown;
  idempotencyKey?: string;
  /** Safe reads only; commands additionally require a durable server receipt/key. */
  retries?: number;
  timeoutMs?: number;
  responseType?: 'json' | 'blob' | 'text';
}
let session: Session | null = null;
let generation = 0;
let bootstrap: Promise<Session> | null = null;
const active = new Set<AbortController>();
const listeners = new Set<() => void>();
export const getSession = () => session;
export const getPrincipalKey = () => session ? `${session.foundation_id}:${session.user_id ?? session.registration_id ?? 'anonymous'}` : 'anonymous';
export function onSessionChange(fn: () => void) { listeners.add(fn); return () => { listeners.delete(fn); }; }
export function clearSession(broadcast = true) {
  generation++; session = null; bootstrap = null;
  active.forEach(c => c.abort()); active.clear();
  listeners.forEach(fn => fn());
  if (broadcast) channel?.postMessage('session-changed');
}
const channel = typeof window !== 'undefined' && typeof BroadcastChannel !== 'undefined' ? new BroadcastChannel('opora-session') : null;
channel?.addEventListener('message', () => clearSession(false));
const failure=readApiError;

export async function initializeSession(force = false): Promise<Session> {
  if (force) clearSession();
  if (session) return session;
  if (bootstrap) return bootstrap;
  const epoch = generation; const controller = new AbortController(); active.add(controller);
  const timer = setTimeout(() => controller.abort(), 12000);
  const pending = (async () => {
    try {
      const response = await fetch(apiPath('/auth/session'), {credentials:'same-origin', cache:'no-store', signal:controller.signal, headers:{Accept:'application/json'}});
      if (!response.ok) throw await failure(response);
      const value = await response.json() as Session;
      if (epoch !== generation) throw new ApiError(0, 'principal_changed', 'Сессия изменилась. Обновите страницу.');
      session = value; listeners.forEach(fn => fn()); return value;
    } catch (error) {
      if (error instanceof ApiError) throw error;
      if (epoch !== generation) throw new ApiError(0, 'principal_changed', 'Сессия изменилась. Обновите страницу.');
      throw new ApiError(0, controller.signal.aborted ? 'timeout' : 'network', 'Не удалось связаться с сервером. Проверьте соединение и попробуйте ещё раз.', {}, undefined, true);
    } finally { clearTimeout(timer); active.delete(controller); if (epoch === generation) bootstrap = null; }
  })();
  bootstrap = pending; return pending;
}
export async function api<T>(path: string, options: ApiOptions = {}): Promise<T> {
  const url = apiPath(path); const method = (options.method ?? 'GET').toUpperCase();
  const safe = ['GET','HEAD','OPTIONS'].includes(method);
  await initializeSession();
  const epoch = generation; const principal = getPrincipalKey();
  const {body, idempotencyKey, retries = safe ? 1 : 0, timeoutMs = safe ? 12000 : 30000, responseType = 'json', ...request} = options;
  const budget = Math.min(Math.max(retries, 0), 2);
  for (let attempt = 0; ; attempt++) {
    if (epoch !== generation || principal !== getPrincipalKey()) throw new ApiError(0, 'principal_changed', 'Сессия изменилась. Повторите действие.');
    const controller = new AbortController(); active.add(controller);
    const abort = () => controller.abort(options.signal?.reason);
    if (options.signal?.aborted) abort(); else options.signal?.addEventListener('abort', abort, {once:true});
    const timer = setTimeout(() => controller.abort('timeout'), Math.min(Math.max(timeoutMs, 100), 120000));
    let retryDelay = 0;
    try {
      const headers = new Headers(request.headers); headers.set('Accept','application/json');
      if (!safe && session?.csrf_token) headers.set('X-CSRF-Token', session.csrf_token);
      if (idempotencyKey) headers.set('Idempotency-Key', idempotencyKey);
      const isRaw = (typeof FormData !== 'undefined' && body instanceof FormData) || (typeof Blob !== 'undefined' && body instanceof Blob) || body instanceof ArrayBuffer || ArrayBuffer.isView(body);
      if (body !== undefined && !isRaw) headers.set('Content-Type','application/json');
      const response = await fetch(url, {...request, method, headers, body:body === undefined ? undefined : isRaw ? body as BodyInit : JSON.stringify(body), credentials:'same-origin', cache:'no-store', signal:controller.signal});
      if (epoch !== generation) throw new ApiError(0, 'principal_changed', 'Сессия изменилась.');
      if (response.status === 401) { clearSession(); throw await failure(response); }
      if (!response.ok) {
        const error = await failure(response);
        const retryAfter = response.headers.get('Retry-After');
        const after = retryAfter ? Number(retryAfter) * 1000 : 0;
        if (response.status >= 500 && attempt < budget && (safe || idempotencyKey) && (!retryAfter || (Number.isFinite(after) && after <= 2000))) retryDelay = Math.max(after, 1);
        else throw error;
      } else {
        const value = response.status === 204 || method === 'HEAD' ? undefined as T : responseType === 'blob' ? await response.blob() as T : responseType === 'text' ? await response.text() as T : await response.json() as T;
        if (epoch !== generation) throw new ApiError(0, 'principal_changed', 'Сессия изменилась.');
        return value;
      }
    } catch (error) {
      if (error instanceof ApiError) throw error;
      if (options.signal?.aborted || epoch !== generation) throw new ApiError(0, epoch !== generation ? 'principal_changed' : 'aborted', 'Запрос отменён.');
      if (attempt < budget && (safe || idempotencyKey)) retryDelay = 1;
      else throw new ApiError(0, controller.signal.aborted ? 'timeout' : 'network', 'Не удалось связаться с сервером. Проверьте соединение.', {}, undefined, true);
    } finally { clearTimeout(timer); active.delete(controller); options.signal?.removeEventListener('abort', abort); }
    await new Promise(resolve => setTimeout(resolve, Math.max(retryDelay, Math.random() * Math.min(2000, 300 * 2 ** attempt))));
  }
}
