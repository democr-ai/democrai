import { useMemo, useSyncExternalStore } from 'react';

import {
  getExternalAccessApprovalRevision,
  subscribeExternalAccessApprovals,
} from '@/runtime/controllers/external_access';
import { resolveMediaUrl } from '@/utils/media';

function appendApprovalRevision(url: string, revision: number): string {
  if (!url || !url.includes('/media/proxy')) return url;

  try {
    const parsed = new URL(url, window.location.origin);
    parsed.searchParams.set('_ea', String(revision));
    return parsed.toString();
  } catch {
    const separator = url.includes('?') ? '&' : '?';
    return `${url}${separator}_ea=${encodeURIComponent(String(revision))}`;
  }
}

export function useResolvedMediaUrl(raw: string): string {
  const approvalRevision = useSyncExternalStore(
    subscribeExternalAccessApprovals,
    getExternalAccessApprovalRevision,
    getExternalAccessApprovalRevision,
  );

  const resolved = useMemo(() => resolveMediaUrl(raw), [raw]);

  return useMemo(() => appendApprovalRevision(resolved, approvalRevision), [resolved, approvalRevision]);
}
