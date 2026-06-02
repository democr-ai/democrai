import React from 'react';
import { parseStyle } from '@/utils/style';
import { getLiteral } from '@/renderers/shared';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Background, Controls, MiniMap, ReactFlow, type Edge, type Node } from '@xyflow/react';
import '@xyflow/react/dist/style.css';

const FLOW_EDGE_RE = /^(?<src>.+?)\s*(?:-->|---|-.->|==>)\s*(?:\|(?<label>[^|]+)\|)?\s*(?<dst>.+)$/;

const parseNode = (input: string): { id: string; label: string } | null => {
  const raw = String(input || '').trim();
  if (!raw) return null;
  const m = raw.match(/^(?<id>[A-Za-z0-9_.:-]+)/);
  if (!m?.groups?.id) return null;
  const id = m.groups.id;
  const rest = raw.slice(m[0].length).trim();
  const label = rest.replace(/[\[\](){}]/g, '').trim() || id;
  return { id, label };
};

const parseMermaid = (mermaid: string): { nodes: any[]; edges: any[] } => {
  const lines = String(mermaid || '').split('\n').map((line) => line.trim()).filter((line) => line && !line.startsWith('%%'));
  const nodes = new Map<string, any>();
  const edges: any[] = [];
  for (const line of lines) {
    if (/^(flowchart|graph)\b/i.test(line)) continue;
    const match = line.match(FLOW_EDGE_RE);
    if (!match?.groups) continue;
    const src = parseNode(match.groups.src);
    const dst = parseNode(match.groups.dst);
    if (!src || !dst) continue;
    if (!nodes.has(src.id)) nodes.set(src.id, src);
    if (!nodes.has(dst.id)) nodes.set(dst.id, dst);
    edges.push({ source: src.id, target: dst.id, label: String(match.groups.label || '').trim() });
  }
  return { nodes: Array.from(nodes.values()), edges };
};

export const Diagram: React.FC<any> = ({ title, nodes = [], edges = [], mermaid, style, height = 360 }) => {
  const parsed = React.useMemo(() => {
    const inlineNodes = Array.isArray(nodes) ? nodes : [];
    const inlineEdges = Array.isArray(edges) ? edges : [];
    if (inlineNodes.length || inlineEdges.length) return { nodes: inlineNodes, edges: inlineEdges };
    return parseMermaid(getLiteral(mermaid));
  }, [nodes, edges, mermaid]);

  const rfNodes = React.useMemo<Node[]>(() => (parsed.nodes || []).map((node: any, idx: number) => ({
    id: String(node?.id || `node_${idx}`),
    data: { label: getLiteral(node?.label || node?.id || `Node ${idx + 1}`) },
    position: node?.position || { x: 80 + ((idx % 4) * 200), y: 50 + (Math.floor(idx / 4) * 120) },
  })), [parsed.nodes]);

  const rfEdges = React.useMemo<Edge[]>(() => (parsed.edges || []).map((edge: any, idx: number) => ({
    id: String(edge?.id || `edge_${idx}`),
    source: String(edge?.source || edge?.from || ''),
    target: String(edge?.target || edge?.to || ''),
    label: getLiteral(edge?.label),
    animated: false,
  })), [parsed.edges]);

  return (
    <Card style={parseStyle(style)}>
      {title ? <CardHeader><CardTitle className="text-sm">{getLiteral(title)}</CardTitle></CardHeader> : null}
      <CardContent>
        <div className="w-full rounded-md border" style={{ height: Math.max(220, Number(height) || 360) }}>
          <ReactFlow nodes={rfNodes} edges={rfEdges} fitView>
            <MiniMap />
            <Controls />
            <Background />
          </ReactFlow>
        </div>
      </CardContent>
    </Card>
  );
};
