import { matchesExternalAccessApproval } from '@/utils/externalAccess';

type ApprovalDecision = 'session' | 'permanent' | 'deny' | string;

export type ExternalAccessApproval = {
  decision: ApprovalDecision;
  resourceType: string;
  moduleName: string;
  target: string;
  createdAt: number;
};

type Listener = () => void;

const listeners = new Set<Listener>();
let approvalRevision = 0;
const recentApprovals: ExternalAccessApproval[] = [];
const MAX_RECENT_APPROVALS = 128;

function emitChange(): void {
  listeners.forEach((listener) => {
    try {
      listener();
    } catch {
      // Ignore a broken listener; store integrity matters more.
    }
  });
}

export function subscribeExternalAccessApprovals(listener: Listener): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function getExternalAccessApprovalRevision(): number {
  return approvalRevision;
}

export function recordExternalAccessDecisionAck(payload: {
  decision?: string;
  resource_type?: string;
  module_name?: string;
  plugin_name?: string;
  target?: string;
}): void {
  const decision = String(payload.decision || '').trim().toLowerCase();
  if (decision !== 'session' && decision !== 'permanent') return;

  const approval: ExternalAccessApproval = {
    decision,
    resourceType: String(payload.resource_type || '').trim().toLowerCase(),
    moduleName: String(payload.module_name || payload.plugin_name || '').trim(),
    target: String(payload.target || '').trim(),
    createdAt: Date.now(),
  };

  recentApprovals.push(approval);
  if (recentApprovals.length > MAX_RECENT_APPROVALS) {
    recentApprovals.splice(0, recentApprovals.length - MAX_RECENT_APPROVALS);
  }

  approvalRevision += 1;
  emitChange();
}

export function hasMatchingApprovedAccess(candidate: {
  resourceType: string;
  moduleName: string;
  target: string;
}): boolean {
  return recentApprovals.some((approval) =>
    matchesExternalAccessApproval(
      {
        resourceType: approval.resourceType,
        moduleName: approval.moduleName,
        target: approval.target,
      },
      candidate,
    ),
  );
}
