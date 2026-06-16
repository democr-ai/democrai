import { matchesExternalAccessApproval } from '@/utils/externalAccess';

export type ExternalAccessPrompt = {
  requestId: string;
  resourceType: string;
  moduleName: string;
  target: string;
  message: string;
  canApprove: boolean;
};

export type ExternalAccessIncident = ExternalAccessPrompt & {
  incidentId: string;
  createdAt: number;
};

export type PendingActionRequest = {
  actionName: string;
  surfaceId: string;
  componentId: string;
  context: Record<string, any>;
  createdAt: number;
};

export type PostponedAction = PendingActionRequest & {
  requestId: string;
  resourceType: string;
  moduleName: string;
  target: string;
};

function buildExternalAccessIncidentId(payload: {
  requestId: string;
  resourceType: string;
  moduleName: string;
  target: string;
}): string {
  const resourceType = String(payload.resourceType || '').trim().toLowerCase();
  const moduleName = String(payload.moduleName || '').trim().toLowerCase();
  const target = String(payload.target || '').trim().toLowerCase();
  const requestId = String(payload.requestId || '').trim().toLowerCase();
  if (requestId) return `req:${requestId}`;
  return `res:${resourceType}|mod:${moduleName}|target:${target}`;
}

export class ExternalAccessCoordinator {
  private incidents: ExternalAccessIncident[] = [];

  private pendingActionPayloads: Record<string, PendingActionRequest> = {};

  private postponedActions: Record<string, PostponedAction> = {};

  clear(): void {
    this.incidents = [];
    this.pendingActionPayloads = {};
    this.postponedActions = {};
  }

  queuePendingAction(requestId: string, payload: PendingActionRequest): void {
    const key = String(requestId || '').trim();
    if (!key) return;
    this.pendingActionPayloads = {
      ...this.pendingActionPayloads,
      [key]: payload,
    };
  }

  releasePendingAction(requestId: string): void {
    const key = String(requestId || '').trim();
    if (!key) return;
    if (!this.pendingActionPayloads[key]) return;
    const next = { ...this.pendingActionPayloads };
    delete next[key];
    this.pendingActionPayloads = next;
  }

  getIncidents(): ExternalAccessIncident[] {
    return this.incidents;
  }

  getFirstIncident(): ExternalAccessIncident | null {
    return this.incidents[0] || null;
  }

  getIncidentById(incidentId: string): ExternalAccessIncident | null {
    const key = String(incidentId || '').trim();
    if (!key) return null;
    return this.incidents.find((entry) => entry.incidentId === key) || null;
  }

  dismissIncident(incidentId: string): ExternalAccessIncident[] {
    const key = String(incidentId || '').trim();
    if (!key) return this.incidents;
    this.incidents = this.incidents.filter((entry) => entry.incidentId !== key);
    return this.incidents;
  }

  noteExternalAccessRequired(incident: ExternalAccessPrompt): ExternalAccessIncident[] {
    const candidate: ExternalAccessIncident = {
      ...incident,
      incidentId: buildExternalAccessIncidentId({
        requestId: incident.requestId,
        resourceType: incident.resourceType,
        moduleName: incident.moduleName,
        target: incident.target,
      }),
      createdAt: Date.now(),
    };

    const existingIdx = this.incidents.findIndex((entry) => entry.incidentId === candidate.incidentId);
    if (existingIdx < 0) {
      this.incidents = [...this.incidents, candidate];
    } else {
      const next = [...this.incidents];
      next[existingIdx] = {
        ...next[existingIdx],
        ...candidate,
        createdAt: next[existingIdx].createdAt || candidate.createdAt,
      };
      this.incidents = next;
    }

    const requestId = String(incident.requestId || '').trim();
    const pendingAction = requestId ? this.pendingActionPayloads[requestId] : null;
    if (requestId && pendingAction) {
      this.postponedActions = {
        ...this.postponedActions,
        [requestId]: {
          requestId,
          actionName: pendingAction.actionName,
          surfaceId: pendingAction.surfaceId,
          componentId: pendingAction.componentId,
          context: { ...pendingAction.context },
          resourceType: incident.resourceType,
          moduleName: incident.moduleName,
          target: incident.target,
          createdAt: Date.now(),
        },
      };
      const nextPendingPayloads = { ...this.pendingActionPayloads };
      delete nextPendingPayloads[requestId];
      this.pendingActionPayloads = nextPendingPayloads;
    }

    return this.incidents;
  }

  noteDecisionAck(payload: {
    decision?: string;
    resource_type?: string;
    module_name?: string;
    plugin_name?: string;
    target?: string;
    approval_request_id?: string;
    request_id?: string;
  }): {
    approved: boolean;
    replayActions: Array<{ requestId: string; action: PostponedAction }>;
    incidents: ExternalAccessIncident[];
  } {
    const decision = String(payload.decision || '').trim().toLowerCase();
    const approved = decision === 'session' || decision === 'permanent';

    const resourceType = String(payload.resource_type || '').trim();
    const moduleName = String(payload.module_name || payload.plugin_name || '').trim();
    const target = String(payload.target || '').trim();

    let replayActions: Array<{ requestId: string; action: PostponedAction }> = [];
    if (approved) {
      const entries = Object.entries(this.postponedActions);
      replayActions = entries.filter(([, action]) =>
        matchesExternalAccessApproval(
          {
            resourceType,
            moduleName,
            target,
          },
          {
            resourceType: action.resourceType,
            moduleName: action.moduleName,
            target: action.target,
          },
        ),
      ).map(([requestId, action]) => ({ requestId, action }));

      if (replayActions.length > 0) {
        const nextPostponed = { ...this.postponedActions };
        replayActions.forEach(({ requestId }) => {
          delete nextPostponed[requestId];
        });
        this.postponedActions = nextPostponed;
      }
    }

    const approvalRequestId = String(payload.approval_request_id || '').trim();
    const messageRequestId = String(payload.request_id || '').trim();
    const incidentRequestId = approvalRequestId || messageRequestId;

    this.incidents = this.incidents.filter((entry) => {
      const entryRequestId = String(entry.requestId || '').trim();
      if (incidentRequestId && entryRequestId === incidentRequestId) {
        return false;
      }

      const hasScopeData = Boolean(resourceType || moduleName || target);
      if (!hasScopeData) {
        return true;
      }

      const sameScope = matchesExternalAccessApproval(
        {
          resourceType,
          moduleName,
          target,
        },
        {
          resourceType: entry.resourceType,
          moduleName: entry.moduleName,
          target: entry.target,
        },
      );
      return !sameScope;
    });

    return {
      approved,
      replayActions,
      incidents: this.incidents,
    };
  }
}
