import {getPrincipalKey} from './transport';
/** All private keys include the current foundation/principal. Slots use staleTime:0. */
export const keys = {
  session: () => ['session'] as const,
  all: (domain: string) => [getPrincipalKey(), domain] as const,
  list: (domain: string, filters: unknown = {}) => [getPrincipalKey(), domain, 'list', filters] as const,
  detail: (domain: string, id: string) => [getPrincipalKey(), domain, 'detail', id] as const,
  self: (domain: string) => [getPrincipalKey(), domain, 'self'] as const,
};
export const queryKeys = keys;
