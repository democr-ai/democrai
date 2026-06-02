import React from 'react';
import { parseStyle } from '@/utils/style';
import { emitActionSpec, getLiteral } from '@/renderers/shared';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
  Background,
  Handle,
  MarkerType,
  ReactFlow,
  type Edge,
  type Node,
  type NodeProps,
  Position,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { DATA_THEME, dataStatusColor } from '@/utils/dataTheme';

type CommitNode = {
  id: string;
  label: string;
  lane: number;
  branch: string;
  color: string;
};

const PALETTE = [
  DATA_THEME.status.planned,
  DATA_THEME.status.active,
  DATA_THEME.status.done,
  DATA_THEME.status.blocked,
  dataStatusColor('queued'),
  DATA_THEME.status.risk,
];

const safeColor = (raw: any, fallback: string): string => {
  const value = String(raw || '').trim();
  if (!value) return fallback;
  if (/^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$/.test(value)) return value;
  return fallback;
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
        if (!key) {
          lane = 0;
        } else {
          if (!branchToLane.has(key)) branchToLane.set(key, branchToLane.size);
          lane = Number(branchToLane.get(key) || 0);
        }
      }

      const fallbackColor = PALETTE[lane % PALETTE.length];
      const color = safeColor(raw?.color, fallbackColor);

      return {
        id,
        label: String(raw?.label || raw?.message || id),
        lane,
        branch,
        color,
      };
    })
    .filter((entry): entry is CommitNode => Boolean(entry));
};

const parseEdges = (rawEdges: any[], commits: CommitNode[]): Array<{ source: string; target: string }> => {
  const ids = new Set(commits.map((entry) => entry.id));
  const explicit = (Array.isArray(rawEdges) ? rawEdges : [])
    .map((raw: any) => ({
      source: String(raw?.source || raw?.from || '').trim(),
      target: String(raw?.target || raw?.to || '').trim(),
    }))
    .filter((entry) => entry.source && entry.target && ids.has(entry.source) && ids.has(entry.target) && entry.source !== entry.target);

  if (explicit.length > 0) return explicit;

  const fallback: Array<{ source: string; target: string }> = [];
  for (let i = 0; i < commits.length - 1; i += 1) {
    fallback.push({ source: commits[i].id, target: commits[i + 1].id });
  }
  return fallback;
};

const GitCommitNode: React.FC<NodeProps<{ label: string; branch: string; color: string }>> = ({ data }) => {
  const branch = String(data?.branch || '').trim();
  return (
    <div className="ui-git-node relative min-w-[320px] rounded-md px-1 py-1">
      <Handle
        type="target"
        position={Position.Top}
        style={{
          opacity: 0,
          width: 1,
          height: 1,
          border: 0,
          background: 'transparent',
          left: 11,
          pointerEvents: 'none',
        }}
      />
      <div className="flex items-start gap-3">
        <span
          className="ui-git-dot mt-1 inline-block h-3.5 w-3.5 rounded-full border shadow"
          style={{ backgroundColor: data?.color || DATA_THEME.status.planned }}
        />
        <div className="min-w-0">
          <div className="ui-git-label truncate text-[12px] font-semibold">{getLiteral(data?.label)}</div>
          {branch ? <div className="ui-git-branch mt-0.5 text-[10px] uppercase tracking-wide">{branch}</div> : null}
        </div>
      </div>
      <Handle
        type="source"
        position={Position.Bottom}
        style={{
          opacity: 0,
          width: 1,
          height: 1,
          border: 0,
          background: 'transparent',
          left: 11,
          pointerEvents: 'none',
        }}
      />
    </div>
  );
};

const nodeTypes = { gitCommit: GitCommitNode };

export const GitGraph: React.FC<any> = ({
  title,
  commits = [],
  edges = [],
  laneWidth = 80,
  rowHeight = 56,
  showLabels = true,
  height = 360,
  action,
  params = {},
  onAction,
  style,
}) => {
  const parsedCommits = React.useMemo(() => parseCommits(Array.isArray(commits) ? commits : []), [commits]);

  const rfNodes = React.useMemo<Node[]>(() => {
    const laneStep = Math.max(56, Number(laneWidth) || 80);
    const rowStep = Math.max(40, Number(rowHeight) || 56);
    return parsedCommits.map((commit, index) => ({
      id: commit.id,
      type: 'gitCommit',
      position: {
        x: 40 + (commit.lane * laneStep),
        y: 24 + (index * rowStep),
      },
      sourcePosition: Position.Bottom,
      targetPosition: Position.Top,
      data: {
        label: showLabels ? commit.label : commit.id,
        branch: commit.branch,
        color: commit.color,
      },
    }));
  }, [parsedCommits, laneWidth, rowHeight, showLabels]);

  const rfEdges = React.useMemo<Edge[]>(() => {
    const graphEdges = parseEdges(Array.isArray(edges) ? edges : [], parsedCommits);
    const commitById = new Map(parsedCommits.map((entry) => [entry.id, entry]));
    const commitIndex = new Map(parsedCommits.map((entry, index) => [entry.id, index]));
    return graphEdges.map((edge, index) => {
      const srcIdx = commitIndex.get(edge.source);
      const dstIdx = commitIndex.get(edge.target);
      const normalized =
        typeof srcIdx === 'number' &&
        typeof dstIdx === 'number' &&
        srcIdx > dstIdx
          ? { source: edge.target, target: edge.source }
          : edge;

      const targetCommit = commitById.get(normalized.target);
      const color = targetCommit?.color || DATA_THEME.status.planned;
      return {
        id: `edge_${index}_${normalized.source}_${normalized.target}`,
        source: normalized.source,
        target: normalized.target,
        type: 'smoothstep',
        style: { stroke: color, strokeWidth: 2.2 },
        markerEnd: {
          type: MarkerType.ArrowClosed,
          color,
          width: 16,
          height: 16,
        },
      } as Edge;
    });
  }, [edges, parsedCommits]);

  return (
    <Card className="w-full" style={{ width: '100%', ...parseStyle(style) }}>
      {title ? (
        <CardHeader>
          <CardTitle className="text-sm">{getLiteral(title)}</CardTitle>
        </CardHeader>
      ) : null}
      <CardContent className="w-full">
        {!parsedCommits.length ? (
          <div className="text-sm text-muted-foreground">No git graph data</div>
        ) : (
          <div className="ui-data-panel ui-gitgraph-shell w-full overflow-hidden rounded-md border" style={{ height: Math.max(220, Number(height) || 360) }}>
            <ReactFlow
              nodes={rfNodes}
              edges={rfEdges}
              nodeTypes={nodeTypes}
              fitView
              nodesDraggable={false}
              nodesConnectable={false}
              elementsSelectable={false}
              onNodeClick={(_event, node) => {
                const commit = parsedCommits.find((entry) => entry.id === node.id);
                emitActionSpec(action, onAction, {
                  ...(params && typeof params === 'object' ? params : {}),
                  source: 'git_graph',
                  commitId: commit?.id,
                  label: commit?.label,
                  branch: commit?.branch,
                  lane: commit?.lane,
                });
              }}
            >
              <Background color="var(--data-git-grid-line)" gap={22} />            </ReactFlow>
          </div>
        )}
      </CardContent>
    </Card>
  );
};
