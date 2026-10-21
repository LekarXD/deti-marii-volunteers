/** Neutral error contracts: no cookie/session channels, storage, or application imports. */
export class ApiError extends Error {
  readonly name = 'ApiError';
  constructor(public status: number, public code: string, message: string,
    public field_errors: Record<string, string> = {}, public current_version?: number,
    public retryable = false, public request_id?: string) { super(message); }
  get statusCode() { return this.status; }
  get fieldErrors() { return this.field_errors; }
}
export async function readApiError(response: Response) {
  // Bounded and deliberately generic if an upstream proxy returns HTML/private details.
  const reader = response.body?.getReader(); let text = ''; let length = 0;
  if (reader) { const decoder = new TextDecoder(); try { while (true) { const part = await reader.read(); if (part.done) break; length += part.value.byteLength; if (length > 65536) { await reader.cancel(); break; } text += decoder.decode(part.value, {stream:true}); } } finally { reader.releaseLock(); } }
  let data: Record<string, unknown> = {}; try { data = JSON.parse(text); } catch { /* generic error */ }
  return new ApiError(response.status, typeof data.code === 'string' ? data.code : 'request_failed',
    typeof data.message === 'string' ? data.message.slice(0, 1000) : 'Не удалось выполнить запрос. Попробуйте ещё раз.',
    typeof data.field_errors === 'object' && data.field_errors ? data.field_errors as Record<string,string> : {},
    typeof data.current_version === 'number' ? data.current_version : undefined, data.retryable === true,
    typeof data.request_id === 'string' ? data.request_id : undefined);
}
