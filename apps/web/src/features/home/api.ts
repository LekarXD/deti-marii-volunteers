import {useMutation, useQueryClient} from '@tanstack/react-query';
import {api} from '../../api/transport';
import {keys} from '../../api/keys';
import type {AssignmentParticipation} from '../activities/participationApi';
import {LATE_TEXT} from './model';

type Command = {path: string; body: unknown};
/** One command per user intent; the schedule, feed and memo are re-read from the server afterwards. */
export function useHomeCommand() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({path, body}: Command) => api<unknown>(path, {method: 'POST', body, idempotencyKey: crypto.randomUUID()}),
    onSuccess: () => Promise.all([
      client.invalidateQueries({queryKey: keys.all('activities')}),
      client.invalidateQueries({queryKey: keys.all('assignment-preparation')}),
    ]),
  });
}
export const confirmCommand = (item: AssignmentParticipation): Command => ({path: `/assignments/${item.id}/confirm`, body: {expected_version: item.version}});
/** An invitation is declined, a confirmed class is cancelled; both take OwnAssignmentDecision. */
export const declineCommand = (item: AssignmentParticipation): Command => ({
  path: `/assignments/${item.id}/${item.allowed_actions.includes('decline') ? 'decline' : 'cancel'}`,
  body: {expected_version: item.version},
});
export const lateCommand = (item: AssignmentParticipation): Command => ({
  path: `/me/assignments/${item.id}/questions`,
  body: {kind: 'question', text: LATE_TEXT, restricted: false},
});
export const canDecline = (item: AssignmentParticipation) => item.allowed_actions.includes('decline') || item.allowed_actions.includes('cancel');
