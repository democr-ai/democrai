import React from 'react';
import { parseStyle } from '@/utils/style';
import { emitActionSpec, getLiteral } from '@/renderers/shared';
import { Card, CardBody, CardHeader, CardTitle } from 'design-react-kit';

type CommitNode = {
  id: string;
  label: string;
  lane: number;
  branch: string;
  color: string;
};

type GraphEdge = {
  source: string;
  target: string;
};

const PALETTE = [
  'var(--primary)',
  'var(--ui-tone-success)',
  'var(--ui-tone-warning)',
  'var(--ui-tone-info)',
  'var(--ui-tone-danger)',
  'var(--muted-foreground)',
];

const safeColor = (raw: any, fallback: string): string => {
  const value = String(raw || '').trim();
  if (!value) return fallback;
  if (/^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$/.test(value)) return value;
  if (/^var\(--[A-Za-z0-9_-]+\)$/.test(value)) return value;
  return fallback;
};

const splitCommitLabel = (label: string): { hash: string; message: string } => {
  const text = String(label || '').trim();
  const match = text.match(/^([0-9a-f]{6,12})\s+(.+)$/i);
  if (!match) return { hash: '', message: text };
  return { hash: match[1], message: match[2] };
};

const parseCommits = (rawCommits: any[]): CommitNode[] => {
  const branchToLane = new Map<string, number>();
  return rawCommits
    .map((raw: any, index: number) => {
      const id = String(raw?.id || `c${index + 1}`).trim();
      if (!id) return null;
      const branch = String(raw?.branch || raw?.laneName || '').trim();
      const laneRaw = Number(raw?.lane);
      let lane = Number.isFinite(laneRaw) ? Math.max(0, Math.trunc(laneRaw)) : -1;
      if (lane < 0) {
        const key = branch.toLowerCase();
        if (!key) lane = 0;
        else {
          if (!branchToLane.has(key)) branchToLane.set(key, branchToLane.size);
          lane = Number(branchToLane.get(key) || 0);
        }
      }
      const fallbackColor = PALETTE[lane % PALETTE.length];
      return { id, label: String(raw?.label || raw?.message || id), lane, branch, color: safeColor(raw?.color, fallbackColor) };
    })
    .filter((entry): entry is CommitNode => Boolean(entry));
};

const parseEdges = (rawEdges: any[], commits: CommitNode[]): GraphEdge[] => {
  const ids = new Set(commits.map((entry) => entry.id));
  const explicit = (Array.isArray(rawEdges) ? rawEdges : [])
    .map((raw: any) => ({ source: String(raw?.source || raw?.from || '').trim(), target: String(raw?.target || raw?.to || '').trim() }))
    .filter((entry) => entry.source && entry.target && ids.has(entry.source) && ids.has(entry.target) && entry.source !== entry.target);
  if (explicit.length > 0) return explicit;
  const fallback: GraphEdge[] = [];
  for (let i = 0; i < commits.length - 1; i += 1) fallback.push({ source: commits[i].id, target: commits[i + 1].id });
  return fallback;
};

const edgePath = (sx: number, sy: number, tx: number, ty: number): string => {
  if (sx === tx) return `M ${sx} ${sy} L ${tx} ${ty}`;
  const midY = sy + Math.max(22, Math.abs(ty - sy) * 0.48);
  return `M ${sx} ${sy} C ${sx} ${midY}, ${tx} ${midY}, ${tx} ${ty}`;
};

export const GitGraph: React.FC<any> = ({
  title,
  commits = [],
  edges = [],
  laneWidth = 104,
  rowHeight = 62,
  showLabels = true,
  showBranchNames = true,
  show_branch_names,
  height = 360,
  action,
  onAction,
  style,
}) => {
  const parsedCommits = React.useMemo(() => parseCommits(Array.isArray(commits) ? commits : []), [commits]);
  const parsedEdges = React.useMemo(() => parseEdges(Array.isArray(edges) ? edges : [], parsedCommits), [edges, parsedCommits]);

  const layout = React.useMemo(() => {
    const laneStep = Math.max(86, Number(laneWidth) || 104);
    const rowStep = Math.max(54, Number(rowHeight) || 62);
    const leftPad = 42;
    const topPad = 54;
    const bottomPad = 36;
    const labelWidth = showLabels ? 320 : 120;
    const maxLane = parsedCommits.reduce((max, commit) => Math.max(max, commit.lane), 0);
    const laneCount = maxLane + 1;
    const laneX = new Map<number, number>();
    Array.from({ length: laneCount }, (_, lane) => lane).forEach((lane) => {
      laneX.set(lane, leftPad + lane * laneStep);
    });
    const commitY = new Map<string, number>();
    parsedCommits.forEach((commit, index) => commitY.set(commit.id, topPad + index * rowStep));
    const width = leftPad * 2 + Math.max(1, laneCount - 1) * laneStep + labelWidth;
    const contentHeight = topPad + Math.max(0, parsedCommits.length - 1) * rowStep + bottomPad;
    return { laneStep, rowStep, leftPad, topPad, bottomPad, labelWidth, laneCount, laneX, commitY, width, contentHeight };
  }, [parsedCommits, laneWidth, rowHeight, showLabels]);

  const branchNames = React.useMemo(() => {
    const names = new Map<number, string>();
    parsedCommits.forEach((commit) => {
      if (!names.has(commit.lane)) names.set(commit.lane, commit.branch || `lane ${commit.lane + 1}`);
    });
    return names;
  }, [parsedCommits]);

  const showBranches = show_branch_names ?? showBranchNames;
  const viewportHeight = Math.max(260, Number(height) || 360);

  return (
    <Card style={parseStyle(style)} className="a2ui-git-graph border overflow-hidden">
      {title && (
        <CardHeader className="a2ui-git-graph-titlebar border-bottom">
          <CardTitle className="m-0 xsmall text-uppercase fw-bold">{getLiteral(title)}</CardTitle>
        </CardHeader>
      )}
      <CardBody className="p-0">
        {!parsedCommits.length ? (
          <div className="p-4 text-center text-muted small">Nessun dato del grafo git disponibile.</div>
        ) : (
          <div className="a2ui-git-graph-scroll overflow-auto" style={{ height: viewportHeight }}>
            <svg
              className="a2ui-git-graph-svg"
              width={layout.width}
              height={layout.contentHeight}
              viewBox={`0 0 ${layout.width} ${layout.contentHeight}`}
              role="img"
              aria-label="git commit graph"
            >
              {Array.from({ length: layout.laneCount }, (_, lane) => {
                const x = layout.laneX.get(lane) || layout.leftPad;
                const name = branchNames.get(lane) || `lane ${lane + 1}`;
                return (
                  <g key={`lane-${lane}`}>
                    <line className="a2ui-git-lane-line" x1={x} y1={layout.topPad - 22} x2={x} y2={layout.contentHeight - layout.bottomPad + 12} />
                    {showBranches && (
                      <g transform={`translate(${x}, ${layout.topPad - 34})`}>
                        <rect className="a2ui-git-branch-pill" x="-36" y="-12" width="72" height="22" rx="0" />
                        <text className="a2ui-git-branch-text" x="0" y="3" textAnchor="middle">{name}</text>
                      </g>
                    )}
                  </g>
                );
              })}

              {parsedEdges.map((edge, index) => {
                const source = parsedCommits.find((commit) => commit.id === edge.source);
                const target = parsedCommits.find((commit) => commit.id === edge.target);
                if (!source || !target) return null;
                const sx = layout.laneX.get(source.lane) || layout.leftPad;
                const tx = layout.laneX.get(target.lane) || layout.leftPad;
                const sy = layout.commitY.get(source.id) || layout.topPad;
                const ty = layout.commitY.get(target.id) || layout.topPad;
                const color = target.color || source.color;
                return (
                  <path
                    key={`${edge.source}-${edge.target}-${index}`}
                    className="a2ui-git-edge"
                    d={edgePath(sx, sy + 13, tx, ty - 13)}
                    style={{ stroke: color }}
                  />
                );
              })}

              {parsedCommits.map((commit) => {
                const x = layout.laneX.get(commit.lane) || layout.leftPad;
                const y = layout.commitY.get(commit.id) || layout.topPad;
                const { hash, message } = splitCommitLabel(getLiteral(commit.label));
                const labelX = x + 22;
                return (
                  <g
                    key={commit.id}
                    className="a2ui-git-commit"
                    tabIndex={0}
                    role="button"
                    aria-label={getLiteral(commit.label)}
                    onClick={() => emitActionSpec(action, onAction, { source: 'git_graph', commitId: commit.id, label: commit.label, branch: commit.branch, lane: commit.lane })}
                    onKeyDown={(event) => {
                      if (event.key === 'Enter' || event.key === ' ') {
                        event.preventDefault();
                        emitActionSpec(action, onAction, { source: 'git_graph', commitId: commit.id, label: commit.label, branch: commit.branch, lane: commit.lane });
                      }
                    }}
                  >
                    <circle className="a2ui-git-commit-ring" cx={x} cy={y} r="12" style={{ stroke: commit.color }} />
                    <circle className="a2ui-git-commit-dot" cx={x} cy={y} r="6" style={{ fill: commit.color }} />
                    {showLabels && (
                      <g transform={`translate(${labelX}, ${y - 18})`}>
                        <rect className="a2ui-git-label-card" x="0" y="0" width={Math.max(220, layout.labelWidth - 34)} height="36" rx="0" />
                        {hash && <text className="a2ui-git-hash" x="10" y="14">{hash}</text>}
                        <text className="a2ui-git-message" x={hash ? 70 : 10} y="14">{message}</text>
                        {commit.branch && <text className="a2ui-git-branch-label" x="10" y="29">{commit.branch}</text>}
                      </g>
                    )}
                  </g>
                );
              })}
            </svg>
          </div>
        )}
      </CardBody>
    </Card>
  );
};
