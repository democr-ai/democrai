export function normalizeUrlScope(value: string): { origin: string; path: string; wildcard: boolean } | null {
  const raw = String(value || '').trim();
  if (!raw) return null;
  try {
    const parsed = new URL(raw);
    const wildcard = parsed.pathname.endsWith('/*') || raw.endsWith('/*');
    const path = wildcard
      ? parsed.pathname.replace(/\*+$/, '').replace(/\/+$/, '')
      : parsed.pathname;
    return {
      origin: `${parsed.protocol}//${parsed.host}`.toLowerCase(),
      path: String(path || '/').toLowerCase(),
      wildcard,
    };
  } catch {
    return null;
  }
}

export function matchesExternalAccessTarget(approvedTarget: string, requestedTarget: string): boolean {
  const approved = String(approvedTarget || '').trim();
  const requested = String(requestedTarget || '').trim();
  if (!approved || !requested) return false;
  if (approved === requested) return true;

  const approvedUrl = normalizeUrlScope(approved);
  const requestedUrl = normalizeUrlScope(requested);
  if (!approvedUrl || !requestedUrl) {
    return approved.startsWith(requested) || requested.startsWith(approved);
  }
  if (approvedUrl.origin !== requestedUrl.origin) return false;
  if (!approvedUrl.wildcard) {
    return approvedUrl.path === requestedUrl.path || approvedUrl.path === '/*';
  }
  if (approvedUrl.path === '') return true;
  return requestedUrl.path.startsWith(approvedUrl.path);
}

export function matchesExternalAccessApproval(
  approval: { resourceType: string; moduleName: string; target: string },
  candidate: { resourceType: string; moduleName: string; target: string },
): boolean {
  const approvalResource = String(approval.resourceType || '').trim().toLowerCase();
  const candidateResource = String(candidate.resourceType || '').trim().toLowerCase();
  if (approvalResource && candidateResource && approvalResource !== candidateResource) return false;

  const approvalModule = String(approval.moduleName || '').trim();
  const candidateModule = String(candidate.moduleName || '').trim();
  if (approvalModule && candidateModule && approvalModule !== candidateModule) return false;

  return matchesExternalAccessTarget(String(approval.target || ''), String(candidate.target || ''));
}

