import React from 'react';
import {
  addEdge,
  applyEdgeChanges,
  applyNodeChanges,
  Background,
  Handle,
  Position,
  MarkerType,
  ConnectionMode,
  ReactFlow,
  type Edge,
  type EdgeChange,
  type Node,
  type NodeProps,
  type NodeChange,
  type NodeTypes,
  type ReactFlowInstance,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';

import { parseStyle } from '@/utils/style';
import { getLiteral, toBoolean } from '@/renderers/shared';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet';
import { Textarea } from '@/components/ui/textarea';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { cn } from '@/lib/utils';
import { DATA_THEME, WORKFLOW_THEME, dataStatusColor } from '@/utils/dataTheme';

type WorkflowNodeLike = {
  id?: string;
  label?: any;
  nodeType?: string;
  status?: string;
  x?: number;
  y?: number;
  position?: { x?: number; y?: number };
  fill?: string;
  stroke?: string;
  textColor?: string;
  config?: Record<string, any>;
  input?: { params?: any[] };
  outputs?: WorkflowOutputLike[];
  allowAddOutput?: boolean;
};

type WorkflowEdgeLike = {
  id?: string;
  source?: string;
  target?: string;
  from?: string;
  to?: string;
  label?: any;
  sourceOutput?: string;
  mapping?: Record<string, any>;
};

type NodeTemplate = {
  id: string;
  label: string;
  nodeType: string;
  status: string;
  fill: string;
  stroke: string;
  textColor: string;
  config: Record<string, any>;
  input: { params: string[] };
  outputs: WorkflowOutputLike[];
  allowAddOutput: boolean;
};

type WorkflowNodeData = {
  label: string;
  nodeType: string;
  status: string;
  stroke: string;
  fill: string;
  textColor: string;
  outputs?: WorkflowOutputLike[];
};

type TemplateTab = 'triggers' | 'components' | 'pipelines';
type WorkflowConditionLike = { value1?: any; operator?: string; value2?: any };
type WorkflowOutputLike = {
  id?: string;
  label?: any;
  params?: any[];
  conditionMode?: string;
  conditions?: WorkflowConditionLike[];
};
type ConditionDraft = { id: string; value1: string; operator: string; value2: string };

const WorkflowNodeCard: React.FC<NodeProps<Node<WorkflowNodeData>>> = ({ data, selected }) => {
  const stroke = coerceColor(data?.stroke, WORKFLOW_THEME.nodeStroke);
  const fill = coerceColor(data?.fill, WORKFLOW_THEME.nodeFill);
  const textColor = coerceColor(data?.textColor, WORKFLOW_THEME.nodeText);
  const outputs = data?.outputs || [];

  return (
    <div
      className="relative min-w-[170px] rounded-md border px-3 py-2 shadow-sm"
      style={{
        borderColor: stroke,
        background: fill,
        color: textColor,
        boxShadow: selected ? WORKFLOW_THEME.nodeShadowSelected : WORKFLOW_THEME.nodeShadow,
      }}
    >
      <Handle id="in" type="target" position={Position.Left} className="!h-2.5 !w-2.5" style={{ borderColor: WORKFLOW_THEME.handleBorder, borderWidth: 1, background: WORKFLOW_THEME.handleIn }} />
      <div className="truncate text-[12px] font-semibold">{String(data?.label || 'Node')}</div>
      <div className="truncate text-[10px] opacity-80">{String(data?.nodeType || 'component')}</div>
      <div className="truncate text-[10px] opacity-70">{String(data?.status || 'ready')}</div>

      {outputs.length === 0 ? (
        <Handle id="out" type="source" isConnectable={true} position={Position.Right} className="!h-2.5 !w-2.5" style={{ borderColor: WORKFLOW_THEME.handleBorder, borderWidth: 1, background: WORKFLOW_THEME.handleOut }} />
      ) : null}

      {outputs.length > 0 ? (
        <div className="mt-2 space-y-1">
          {outputs.map((out, idx) => {
            const top = `${((idx + 1) * 100) / (outputs.length + 1)}%`;
            return (
              <div key={out.id} className="relative flex justify-end">
                <span className="pr-1 text-[9px] font-medium opacity-60 uppercase tracking-tighter">{out.label}</span>
                <Handle
                  id={String(out.id)}
                  type="source"
                  position={Position.Right}
                  style={{ top, borderColor: WORKFLOW_THEME.handleBorder, borderWidth: 1, background: WORKFLOW_THEME.handleOut }}
                  className="!h-2.5 !w-2.5"
                />
              </div>
            );
          })}
        </div>
      ) : null}
    </div>
  );
};

// Node types defined outside to avoid re-creation on every render
const WORKFLOW_NODE_TYPES: NodeTypes = {
  workflowNode: WorkflowNodeCard,
};

const DEFAULT_GENERIC_TEMPLATE: NodeTemplate = {
  id: 'generic_component',
  label: 'Generic Component',
  nodeType: 'component',
  status: 'ready',
  fill: WORKFLOW_THEME.nodeFill,
  stroke: WORKFLOW_THEME.nodeStroke,
  textColor: WORKFLOW_THEME.nodeText,
  config: {},
  input: { params: [] },
  outputs: [{ id: 'out_1', label: 'out_1', params: [] }],
  allowAddOutput: true,
};

const DEFAULT_FLOW_NODES: WorkflowNodeLike[] = [
  {
    id: 'webhook',
    label: 'Webhook Trigger',
    nodeType: 'trigger',
    status: 'ready',
    fill: WORKFLOW_THEME.nodeFill,
    stroke: dataStatusColor('planned', WORKFLOW_THEME.nodeStroke),
    textColor: WORKFLOW_THEME.nodeText,
    x: 80,
    y: 180,
    config: { method: 'POST', path: '/tickets/new' },
    outputs: [{ id: 'payload', label: 'payload', params: ['body', 'headers'] }],
  },
  {
    id: 'sanitize',
    label: 'Sanitize Input',
    nodeType: 'transform',
    status: 'ready',
    fill: WORKFLOW_THEME.nodeFill,
    stroke: dataStatusColor('active', WORKFLOW_THEME.nodeStroke),
    textColor: WORKFLOW_THEME.nodeText,
    x: 360,
    y: 180,
    input: { params: ['body', 'headers'] },
    outputs: [{ id: 'normalized', label: 'normalized', params: ['email', 'subject', 'priority'] }],
  },
  {
    id: 'classifier',
    label: 'Priority Classifier',
    nodeType: 'ai',
    status: 'ready',
    fill: WORKFLOW_THEME.nodeFill,
    stroke: dataStatusColor('success', WORKFLOW_THEME.nodeStroke),
    textColor: WORKFLOW_THEME.nodeText,
    x: 640,
    y: 180,
    input: { params: ['email', 'subject', 'priority'] },
    outputs: [
      { id: 'high', label: 'high', params: ['ticket_id', 'priority', 'email'] },
      { id: 'normal', label: 'normal', params: ['ticket_id', 'priority', 'email'] },
    ],
  },
];

const DEFAULT_FLOW_EDGES: WorkflowEdgeLike[] = [
  { source: 'webhook', target: 'sanitize', sourceOutput: 'payload', label: 'payload' },
  { source: 'sanitize', target: 'classifier', sourceOutput: 'normalized', label: 'normalized' },
];

const coerceColor = (value: any, fallback: string): string => {
  const text = String(value || '').trim();
  return text || fallback;
};

const gridPosition = (index: number) => ({
  x: 80 + ((index % 4) * 260),
  y: 50 + (Math.floor(index / 4) * 170),
});

const toFiniteNumber = (value: any, fallback: number): number => {
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  if (typeof value === 'string') {
    const parsed = Number.parseFloat(value.trim());
    if (Number.isFinite(parsed)) return parsed;
  }
  return fallback;
};

const normalizeCanvasCoord = (value: number, fallback: number): number => {
  if (!Number.isFinite(value)) return fallback;
  if (Math.abs(value) > 10000) return fallback;
  return value;
};

const endpointToId = (value: any): string => {
  if (typeof value === 'string' || typeof value === 'number') {
    return String(value).trim();
  }
  if (value && typeof value === 'object') {
    const candidate = value.id ?? value.nodeId ?? value.node ?? value.key ?? value.name ?? '';
    return String(candidate).trim();
  }
  return '';
};

const outputHandleToId = (value: any): string => {
  if (typeof value === 'string' || typeof value === 'number') return String(value).trim();
  if (value && typeof value === 'object') {
    const candidate = value.id ?? value.output ?? value.name ?? '';
    return String(candidate).trim();
  }
  return '';
};

const stableSerialize = (value: any): string => {
  try {
    return JSON.stringify(value);
  } catch {
    return '';
  }
};

const createConditionDraft = (): ConditionDraft => ({
  id: `cond_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
  value1: '',
  operator: '==',
  value2: '',
});

const normalizeTemplates = (raw: any[]): NodeTemplate[] => {
  if (!Array.isArray(raw)) return [];
  const seenIds = new Map<string, number>();
  return raw
    .map((entry: any, index: number) => {
      if (!entry || typeof entry !== 'object') return null;
      const baseId = String(entry.id || `template_${index + 1}`).trim();
      if (!baseId) return null;

      const occurrence = seenIds.get(baseId) || 0;
      seenIds.set(baseId, occurrence + 1);
      const id = occurrence === 0 ? baseId : `${baseId}__${occurrence + 1}`;

      const outputs = Array.isArray(entry.outputs)
        ? entry.outputs
          .map((out: any, outIdx: number) => {
            if (!out || typeof out !== 'object') return null;
            const outputId = String(out.id || `out_${outIdx + 1}`).trim();
            if (!outputId) return null;
            const params = Array.isArray(out.params)
              ? out.params.map((v: any) => String(v || '').trim()).filter(Boolean)
              : [];
            return {
              id: outputId,
              label: String(getLiteral(out.label || outputId)).trim() || outputId,
              params,
            };
          })
          .filter((out): out is { id: string; label: string; params: string[] } => Boolean(out))
        : [];

      const inputParams = Array.isArray(entry.input?.params)
        ? entry.input.params.map((v: any) => String(v || '').trim()).filter(Boolean)
        : [];

      return {
        id,
        label: String(getLiteral(entry.label || id)).trim() || id,
        nodeType: String(entry.nodeType || entry.type || 'component').trim() || 'component',
        status: String(entry.status || 'ready').trim().toLowerCase() || 'ready',
        fill: coerceColor(entry.fill, WORKFLOW_THEME.nodeFill),
        stroke: coerceColor(entry.stroke, WORKFLOW_THEME.nodeStroke),
        textColor: coerceColor(entry.textColor, WORKFLOW_THEME.nodeText),
        config: entry.config && typeof entry.config === 'object' ? entry.config : {},
        input: { params: inputParams },
        outputs: outputs.length ? outputs : [{ id: 'out_1', label: 'out_1', params: [] }],
        allowAddOutput: toBoolean(entry.allowAddOutput ?? true),
      };
    })
    .filter((entry): entry is NodeTemplate => Boolean(entry));
};

const normalizeNodeModel = (node: WorkflowNodeLike): WorkflowNodeLike => {
  const outputs = Array.isArray(node?.outputs)
    ? node.outputs.map((out: any, idx: number) => ({
      id: String(out?.id || `out_${idx + 1}`),
      label: getLiteral(out?.label || out?.id || `out_${idx + 1}`),
      params: Array.isArray(out?.params) ? out.params : [],
      conditionMode: String(out?.conditionMode || 'AND'),
      conditions: Array.isArray(out?.conditions)
        ? out.conditions.map((entry: any) => ({
          value1: String(entry?.value1 || '').trim(),
          operator: String(entry?.operator || '==').trim() || '==',
          value2: String(entry?.value2 || '').trim(),
        })).filter((entry: any) => entry.value1 || entry.value2)
        : [],
    }))
    : [{ id: 'out_1', label: 'out_1', params: [] }];

  return {
    ...node,
    id: String(node?.id || ''),
    label: getLiteral(node?.label || node?.id || 'Node'),
    nodeType: String(node?.nodeType || 'component'),
    status: String(node?.status || 'ready').toLowerCase(),
    fill: coerceColor(node?.fill, WORKFLOW_THEME.nodeFill),
    stroke: coerceColor(node?.stroke, WORKFLOW_THEME.nodeStroke),
    textColor: coerceColor(node?.textColor, WORKFLOW_THEME.nodeText),
    config: node?.config && typeof node.config === 'object' ? node.config : {},
    input: { params: Array.isArray(node?.input?.params) ? node.input!.params : [] },
    outputs,
    allowAddOutput: toBoolean(node?.allowAddOutput ?? true),
  };
};

const normalizeEdgeModel = (edge: WorkflowEdgeLike, index: number): WorkflowEdgeLike | null => {
  const source = endpointToId(edge?.source) || endpointToId(edge?.from);
  const target = endpointToId(edge?.target) || endpointToId(edge?.to);
  if (!source || !target) return null;

  const sourceOutput = outputHandleToId(edge?.sourceOutput);
  const explicitLabel = getLiteral(edge?.label || '');
  const baseId = String(edge?.id || '').trim() || `edge_${source}_${target}_${sourceOutput || 'default'}`;
  return {
    ...edge,
    id: baseId,
    source,
    target,
    label: explicitLabel || sourceOutput,
    sourceOutput,
    mapping: edge?.mapping && typeof edge.mapping === 'object' ? edge.mapping : {},
  };
};

const sanitizeNodeModels = (raw: WorkflowNodeLike[]): WorkflowNodeLike[] => {
  const seen = new Map<string, number>();
  return raw.map((entry, index) => {
    const base = String(entry?.id || `node_${index + 1}`).trim() || `node_${index + 1}`;
    const count = seen.get(base) || 0;
    seen.set(base, count + 1);
    const id = count === 0 ? base : `${base}__${count + 1}`;
    return normalizeNodeModel({
      ...entry,
      id,
    });
  });
};

const sanitizeEdgeModels = (raw: WorkflowEdgeLike[]): WorkflowEdgeLike[] => {
  const seen = new Map<string, number>();
  return raw.map((entry, index) => {
    const source = String(entry?.source || entry?.from || '').trim();
    const target = String(entry?.target || entry?.to || '').trim();
    const sourceOutput = String(entry?.sourceOutput || '').trim();
    const base = String(entry?.id || '').trim() || `edge_${source}_${target}_${sourceOutput || 'default'}`;
    const count = seen.get(base) || 0;
    seen.set(base, count + 1);
    const id = count === 0 ? base : `${base}__${count + 1}`;
    return {
      ...entry,
      id,
      source,
      target,
      sourceOutput,
    };
  });
};

const mapNodeToRF = (node: WorkflowNodeLike, index: number, nodeWidth: number, nodeHeight: number): Node<WorkflowNodeData> => {
  const id = String(node.id || `node_${index}`);
  const pos = node.position || {};
  const fallback = gridPosition(index);
  const x = normalizeCanvasCoord(toFiniteNumber(pos?.x ?? node.x, fallback.x), fallback.x);
  const y = normalizeCanvasCoord(toFiniteNumber(pos?.y ?? node.y, fallback.y), fallback.y);
  const width = Math.max(160, Number(nodeWidth) || 214);
  const height = Math.max(72, Number(nodeHeight) || 92);

  return {
    id,
    type: 'workflowNode',
    data: {
      label: String(getLiteral(node.label || id)),
      nodeType: String(node.nodeType || 'component'),
      status: String(node.status || 'ready'),
      stroke: coerceColor(node.stroke, WORKFLOW_THEME.nodeStroke),
      fill: coerceColor(node.fill, WORKFLOW_THEME.nodeFill),
      textColor: coerceColor(node.textColor, WORKFLOW_THEME.nodeText),
      outputs: node.outputs as any,
    },
    position: {
      x,
      y,
    },
    sourcePosition: Position.Right,
    targetPosition: Position.Left,
    width,
    height: Math.max(height, 92 + (Array.isArray(node.outputs) ? node.outputs.length * 14 : 0)),
    draggable: true,
    selectable: true,
  };
};

const mapEdgeToRF = (edge: WorkflowEdgeLike): Edge => ({
  id: String(edge.id),
  source: String(edge.source || ''),
  target: String(edge.target || ''),
  sourceHandle: String(edge.sourceOutput || 'out'),
  targetHandle: 'in',
  label: '',
  markerEnd: { type: MarkerType.ArrowClosed },
  animated: false,
  selectable: true,
  hidden: false,
  zIndex: 2,
  style: {
    stroke: WORKFLOW_THEME.nodeStroke,
    strokeWidth: 1.8,
  },
});

export const Workflow: React.FC<any> = ({
  title,
  nodes = [],
  edges = [],
  triggers = [],
  components = [],
  pipelines = [],
  componentCatalog = [],
  style,
  height = 560,
  nodeWidth = 214,
  nodeHeight = 92,
  onAction,
  emitActionEvents = false,
}) => {
  const [rfInstance, setRfInstance] = React.useState<ReactFlowInstance | null>(null);
  const emitWorkflowAction = React.useCallback((name: string, payload: Record<string, any>) => {
    if (!emitActionEvents) return;
    onAction?.(name, payload);
  }, [emitActionEvents, onAction]);

  const initialNodeModels = React.useMemo<WorkflowNodeLike[]>(() => {
    const sourceNodes = Array.isArray(nodes)
      ? nodes
      : nodes && typeof nodes === 'object'
        ? Object.values(nodes)
        : [];
    const normalized = sanitizeNodeModels(sourceNodes.map((entry: any) => normalizeNodeModel(entry)));
    if (normalized.length > 0) return normalized;
    return sanitizeNodeModels(DEFAULT_FLOW_NODES.map((entry) => normalizeNodeModel(entry)));
  }, [nodes]);

  const initialEdgeModels = React.useMemo<WorkflowEdgeLike[]>(() => {
    const sourceEdges = Array.isArray(edges)
      ? edges
      : edges && typeof edges === 'object'
        ? Object.values(edges)
        : [];
    const normalized = sourceEdges
      .map((entry: any, index: number) => normalizeEdgeModel(entry, index))
      .filter((entry): entry is WorkflowEdgeLike => Boolean(entry));
    if (normalized.length > 0) return sanitizeEdgeModels(normalized);
    const sourceNodes = Array.isArray(nodes)
      ? nodes
      : nodes && typeof nodes === 'object'
        ? Object.values(nodes)
        : [];
    // Use demo defaults only when no workflow payload is provided at all.
    if (sourceEdges.length === 0 && sourceNodes.length === 0) {
      return sanitizeEdgeModels(DEFAULT_FLOW_EDGES
        .map((entry, index) => normalizeEdgeModel(entry, index))
        .filter((entry): entry is WorkflowEdgeLike => Boolean(entry)));
    }
    return [];
  }, [edges, nodes]);

  const [nodeModels, setNodeModels] = React.useState<WorkflowNodeLike[]>(initialNodeModels);
  const [edgeModels, setEdgeModels] = React.useState<WorkflowEdgeLike[]>(initialEdgeModels);
  const [selectedNodeId, setSelectedNodeId] = React.useState<string>('');
  const [selectedEdgeId, setSelectedEdgeId] = React.useState<string>('');
  const [activeTemplateTab, setActiveTemplateTab] = React.useState<TemplateTab>('components');
  const [selectedTemplateByTab, setSelectedTemplateByTab] = React.useState<Record<TemplateTab, string>>({
    triggers: '',
    components: '',
    pipelines: '',
  });
  const [isAddModalOpen, setIsAddModalOpen] = React.useState(false);
  const [isSelectionDrawerOpen, setIsSelectionDrawerOpen] = React.useState(false);
  const [edgeMappingDraft, setEdgeMappingDraft] = React.useState<string>('');
  const [connectSourceOutput, setConnectSourceOutput] = React.useState<string>('');
  const [connectTargetNodeId, setConnectTargetNodeId] = React.useState<string>('');
  const [newOutputId, setNewOutputId] = React.useState<string>('');
  const [newOutputMode, setNewOutputMode] = React.useState<string>('AND');
  const [newOutputConditions, setNewOutputConditions] = React.useState<ConditionDraft[]>([createConditionDraft()]);
  const lastIncomingNodesSigRef = React.useRef<string>('');
  const lastIncomingEdgesSigRef = React.useRef<string>('');

  React.useEffect(() => {
    const incomingSig = stableSerialize(initialNodeModels);
    if (incomingSig === lastIncomingNodesSigRef.current) return;
    lastIncomingNodesSigRef.current = incomingSig;
    setNodeModels((prev) => (stableSerialize(prev) === incomingSig ? prev : initialNodeModels));
  }, [initialNodeModels]);

  React.useEffect(() => {
    const incomingSig = stableSerialize(initialEdgeModels);
    if (incomingSig === lastIncomingEdgesSigRef.current) return;
    lastIncomingEdgesSigRef.current = incomingSig;
    setEdgeModels((prev) => (stableSerialize(prev) === incomingSig ? prev : initialEdgeModels));
  }, [initialEdgeModels]);

  const templatesByTab = React.useMemo<Record<TemplateTab, NodeTemplate[]>>(() => {
    const triggerTemplates = normalizeTemplates(Array.isArray(triggers) ? triggers : []);
    const componentTemplates = normalizeTemplates([
      ...(Array.isArray(components) ? components : []),
      ...(Array.isArray(componentCatalog) ? componentCatalog : []),
    ]);
    const pipelineTemplates = normalizeTemplates(Array.isArray(pipelines) ? pipelines : []);

    if (triggerTemplates.length === 0 && componentTemplates.length === 0 && pipelineTemplates.length === 0) {
      return {
        triggers: [],
        components: [DEFAULT_GENERIC_TEMPLATE],
        pipelines: [],
      };
    }

    return {
      triggers: triggerTemplates,
      components: componentTemplates,
      pipelines: pipelineTemplates,
    };
  }, [componentCatalog, components, pipelines, triggers]);

  const templates = React.useMemo(
    () => [...templatesByTab.triggers, ...templatesByTab.components, ...templatesByTab.pipelines],
    [templatesByTab],
  );

  React.useEffect(() => {
    setSelectedTemplateByTab((prev) => ({
      triggers: templatesByTab.triggers.some((entry) => entry.id === prev.triggers)
        ? prev.triggers
        : (templatesByTab.triggers[0]?.id || ''),
      components: templatesByTab.components.some((entry) => entry.id === prev.components)
        ? prev.components
        : (templatesByTab.components[0]?.id || ''),
      pipelines: templatesByTab.pipelines.some((entry) => entry.id === prev.pipelines)
        ? prev.pipelines
        : (templatesByTab.pipelines[0]?.id || ''),
    }));
  }, [templatesByTab]);

  React.useEffect(() => {
    if (templatesByTab[activeTemplateTab].length > 0) return;
    if (templatesByTab.triggers.length > 0) {
      setActiveTemplateTab('triggers');
      return;
    }
    if (templatesByTab.components.length > 0) {
      setActiveTemplateTab('components');
      return;
    }
    if (templatesByTab.pipelines.length > 0) {
      setActiveTemplateTab('pipelines');
    }
  }, [activeTemplateTab, templatesByTab]);

  const selectedNode = React.useMemo(
    () => nodeModels.find((entry) => String(entry.id) === selectedNodeId) || null,
    [nodeModels, selectedNodeId],
  );

  const selectedEdge = React.useMemo(
    () => edgeModels.find((entry) => String(entry.id) === selectedEdgeId) || null,
    [edgeModels, selectedEdgeId],
  );

  const connectSourceOptions = React.useMemo(
    () => (selectedNode?.outputs || [])
      .map((out) => ({ value: String(out.id || '').trim(), label: String(out.label || out.id || '').trim() }))
      .filter((out) => out.value),
    [selectedNode],
  );

  const connectTargetOptions = React.useMemo(
    () => nodeModels
      .filter((entry) => String(entry.id || '') && String(entry.id || '') !== String(selectedNode?.id || ''))
      .map((entry) => ({
        value: String(entry.id || ''),
        label: String(entry.label || entry.id || ''),
      })),
    [nodeModels, selectedNode],
  );

  const isEvaluatorSelected = React.useMemo(
    () => String(selectedNode?.nodeType || '').trim().toLowerCase() === 'evaluator',
    [selectedNode],
  );

  React.useEffect(() => {
    setIsSelectionDrawerOpen(Boolean(selectedNode || selectedEdge));
  }, [selectedNode, selectedEdge]);

  React.useEffect(() => {
    if (!selectedEdge) {
      setEdgeMappingDraft('');
      return;
    }
    setEdgeMappingDraft(JSON.stringify(selectedEdge.mapping || {}, null, 2));
  }, [selectedEdge]);

  React.useEffect(() => {
    if (!selectedNode) {
      setConnectSourceOutput('');
      setConnectTargetNodeId('');
      return;
    }
    setConnectSourceOutput((prev) =>
      connectSourceOptions.some((opt) => opt.value === prev) ? prev : (connectSourceOptions[0]?.value || ''),
    );
    setConnectTargetNodeId((prev) =>
      connectTargetOptions.some((opt) => opt.value === prev) ? prev : (connectTargetOptions[0]?.value || ''),
    );
  }, [connectSourceOptions, connectTargetOptions, selectedNode]);

  const rfNodes = React.useMemo<Node<WorkflowNodeData>[]>(
    () => nodeModels.map((entry, index) => mapNodeToRF(entry, index, Number(nodeWidth) || 214, Number(nodeHeight) || 92)),
    [nodeHeight, nodeModels, nodeWidth],
  );
  const rfNodesSignature = React.useMemo(() => stableSerialize(rfNodes), [rfNodes]);
  const [uiNodes, setUiNodes] = React.useState<Node<WorkflowNodeData>[]>(rfNodes);
  const lastUiNodesSyncSigRef = React.useRef<string>('');

  React.useEffect(() => {
    if (rfNodesSignature === lastUiNodesSyncSigRef.current) return;
    lastUiNodesSyncSigRef.current = rfNodesSignature;
    setUiNodes(rfNodes);
  }, [rfNodes, rfNodesSignature]);

  const rfEdges = React.useMemo<Edge[]>(
    () => edgeModels.map((entry) => mapEdgeToRF(entry)),
    [edgeModels],
  );

  const edgeDiagnostics = React.useMemo(() => {
    const nodeIds = new Set(uiNodes.map((n) => String(n.id)));
    let invalid = 0;
    for (const edge of rfEdges) {
      if (!nodeIds.has(String(edge.source)) || !nodeIds.has(String(edge.target))) invalid += 1;
    }
    return {
      total: rfEdges.length,
      invalid,
      valid: rfEdges.length - invalid,
    };
  }, [rfEdges, uiNodes]);

  const onNodesChange = React.useCallback((changes: NodeChange<Node>[]) => {
    setUiNodes((prevUiNodes) => {
      const changedUiNodes = applyNodeChanges(changes, prevUiNodes as any) as Node<WorkflowNodeData>[];

      const structural = changes.some((change) =>
        change.type === 'add' || change.type === 'remove' || change.type === 'replace');
      if (structural) {
        setNodeModels((prevModels) => {
          const remapped = changedUiNodes.map((node) => {
            const original = prevModels.find((entry) => String(entry.id) === String(node.id));
            return normalizeNodeModel({
              ...(original || {}),
              id: String(node.id),
              position: { x: node.position.x, y: node.position.y },
              x: node.position.x,
              y: node.position.y,
            });
          });
          return sanitizeNodeModels(remapped);
        });
      }

      return changedUiNodes;
    });
  }, []);

  const onNodeDragStop = React.useCallback((_: any, node: Node<WorkflowNodeData>) => {
    const nodeId = String(node.id || '');
    if (!nodeId) return;
    setNodeModels((prev) => prev.map((entry) => {
      if (String(entry.id) !== nodeId) return entry;
      return normalizeNodeModel({
        ...entry,
        x: node.position.x,
        y: node.position.y,
        position: { x: node.position.x, y: node.position.y },
      });
    }));
  }, []);

  const onEdgesChange = React.useCallback((changes: EdgeChange<Edge>[]) => {
    const structural = changes.some((change) => change.type === 'remove' || change.type === 'add' || change.type === 'replace');
    if (!structural) return;
    setEdgeModels((prev) => {
      const current = prev.map((entry) => mapEdgeToRF(entry));
      const changed = applyEdgeChanges(changes, current);
      return sanitizeEdgeModels(changed
        .map((edge, index) => normalizeEdgeModel({
          id: String(edge.id),
          source: String(edge.source),
          target: String(edge.target),
          sourceOutput: String((edge as any).sourceHandle || ''),
          label: edge.label,
        }, index))
        .filter((entry): entry is WorkflowEdgeLike => Boolean(entry)));
    });
  }, []);

  const onConnect = React.useCallback((params: any) => {
    if (!params?.source || !params?.target || params.source === params.target) return;
    setEdgeModels((prev) => {
      const current = prev.map((entry) => mapEdgeToRF(entry));
      const next = addEdge(
        {
          ...params,
          sourceHandle: String(params?.sourceHandle || 'out'),
          targetHandle: 'in',
          markerEnd: { type: MarkerType.ArrowClosed },
        },
        current,
      );
      return sanitizeEdgeModels(next
        .map((edge, index) => normalizeEdgeModel({
          id: String(edge.id || `edge_${index}`),
          source: String(edge.source),
          target: String(edge.target),
          sourceOutput: String((edge as any).sourceHandle || ''),
          label: edge.label,
        }, index))
        .filter((entry): entry is WorkflowEdgeLike => Boolean(entry)));
    });
  }, []);

  const addNodeFromTemplate = React.useCallback((templateId?: string) => {
    const resolvedTemplateId = String(templateId || selectedTemplateByTab[activeTemplateTab] || '').trim();
    if (!resolvedTemplateId) return;
    const template = templates.find((entry) => entry.id === resolvedTemplateId);
    if (!template) return;

    const index = nodeModels.length;
    const pos = gridPosition(index);
    const baseId = `${template.id}_${index + 1}`;
    const uniqueId = nodeModels.some((entry) => String(entry.id) === baseId)
      ? `${baseId}_${Date.now()}`
      : baseId;

    const nextNode = normalizeNodeModel({
      id: uniqueId,
      label: template.label,
      nodeType: template.nodeType,
      status: template.status,
      fill: template.fill,
      stroke: template.stroke,
      textColor: template.textColor,
      config: template.config,
      input: { params: template.input.params },
      outputs: template.outputs,
      allowAddOutput: template.allowAddOutput,
      x: pos.x,
      y: pos.y,
    });

    setNodeModels((prev) => [...prev, nextNode]);
    setSelectedNodeId(uniqueId);
    setSelectedEdgeId('');
    setIsAddModalOpen(false);
    emitWorkflowAction('workflow_add_node', { node: nextNode });
  }, [activeTemplateTab, emitWorkflowAction, nodeModels, selectedTemplateByTab, templates]);

  const applyAutoLayout = React.useCallback(() => {
    setNodeModels((prev) =>
      prev.map((entry, index) => {
        const pos = gridPosition(index);
        return normalizeNodeModel({
          ...entry,
          x: pos.x,
          y: pos.y,
          position: { x: pos.x, y: pos.y },
        });
      }),
    );
    setTimeout(() => rfInstance?.fitView({ duration: 180, padding: 0.2 }), 0);
    emitWorkflowAction('workflow_auto_layout', {});
  }, [emitWorkflowAction, rfInstance]);

  const fitCanvas = React.useCallback(() => {
    rfInstance?.fitView({ duration: 180, padding: 0.2 });
  }, [rfInstance]);

  const deleteSelectedNode = React.useCallback(() => {
    const nodeId = String(selectedNodeId || '');
    if (!nodeId) return;

    setNodeModels((prev) => prev.filter((entry) => String(entry.id) !== nodeId));
    setUiNodes((prev) => prev.filter((entry) => String(entry.id) !== nodeId));
    setEdgeModels((prev) =>
      prev.filter((entry) => String(entry.source) !== nodeId && String(entry.target) !== nodeId));

    setSelectedNodeId('');
    setSelectedEdgeId('');
    setIsSelectionDrawerOpen(false);
    emitWorkflowAction('workflow_delete_node', { nodeId });
  }, [emitWorkflowAction, selectedNodeId]);

  const deleteSelectedEdge = React.useCallback(() => {
    const edgeId = String(selectedEdgeId || '');
    if (!edgeId) return;

    setEdgeModels((prev) => prev.filter((entry) => String(entry.id) !== edgeId));
    setSelectedEdgeId('');
    setSelectedNodeId('');
    setIsSelectionDrawerOpen(false);
    emitWorkflowAction('workflow_delete_edge', { edgeId });
  }, [emitWorkflowAction, selectedEdgeId]);

  const applyEdgeMapping = React.useCallback(() => {
    const edgeId = String(selectedEdgeId || '');
    if (!edgeId) return;
    let parsed: Record<string, any> = {};
    try {
      parsed = edgeMappingDraft.trim() ? JSON.parse(edgeMappingDraft) : {};
    } catch {
      return;
    }
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return;
    const normalized = Object.fromEntries(
      Object.entries(parsed)
        .map(([key, value]) => [String(key).trim(), String(value ?? '').trim()])
        .filter(([key, value]) => key && value),
    );
    setEdgeModels((prev) => prev.map((entry) =>
      String(entry.id) === edgeId
        ? { ...entry, mapping: normalized }
        : entry));
    emitWorkflowAction('workflow_apply_mapping', { edgeId, mapping: normalized });
  }, [edgeMappingDraft, emitWorkflowAction, selectedEdgeId]);

  const connectSelectedOutput = React.useCallback(() => {
    if (!selectedNode) return;
    const sourceId = String(selectedNode.id || '');
    const sourceOutput = String(connectSourceOutput || '').trim();
    const targetId = String(connectTargetNodeId || '').trim();
    if (!sourceId || !sourceOutput || !targetId || sourceId === targetId) return;

    const sourceOut = (selectedNode.outputs || []).find((out) => String(out.id || '') === sourceOutput);
    const targetNode = nodeModels.find((entry) => String(entry.id || '') === targetId);
    const sourceParams = Array.isArray(sourceOut?.params) ? sourceOut!.params.map((v) => String(v || '').trim()).filter(Boolean) : [];
    const targetParams = Array.isArray(targetNode?.input?.params) ? targetNode!.input!.params!.map((v) => String(v || '').trim()).filter(Boolean) : [];
    const mapping: Record<string, string> = {};
    for (const param of targetParams) {
      if (sourceParams.includes(param)) mapping[param] = param;
    }

    setEdgeModels((prev) => {
      const exists = prev.some((edge) =>
        String(edge.source) === sourceId &&
        String(edge.target) === targetId &&
        String(edge.sourceOutput || '') === sourceOutput);
      if (exists) return prev;
      const nextEdge = normalizeEdgeModel(
        { source: sourceId, target: targetId, sourceOutput, label: sourceOutput, mapping },
        prev.length,
      );
      if (!nextEdge) return prev;
      return sanitizeEdgeModels([...prev, nextEdge]);
    });
    emitWorkflowAction('workflow_connect_output', { sourceId, sourceOutput, targetId, mapping });
  }, [connectSourceOutput, connectTargetNodeId, emitWorkflowAction, nodeModels, selectedNode]);

  const addConditionRow = React.useCallback(() => {
    setNewOutputConditions((prev) => [...prev, createConditionDraft()]);
  }, []);

  const removeConditionRow = React.useCallback((conditionId: string) => {
    setNewOutputConditions((prev) => {
      const next = prev.filter((entry) => entry.id !== conditionId);
      return next.length > 0 ? next : [createConditionDraft()];
    });
  }, []);

  const updateConditionRow = React.useCallback(
    (conditionId: string, field: 'value1' | 'operator' | 'value2', value: string) => {
      setNewOutputConditions((prev) => prev.map((entry) =>
        entry.id === conditionId
          ? { ...entry, [field]: value }
          : entry));
    },
    [],
  );

  const removeConditionalOutput = React.useCallback((outputId: string) => {
    const nodeId = String(selectedNode?.id || '');
    const normalizedOutputId = String(outputId || '').trim();
    if (!nodeId || !normalizedOutputId) return;

    setNodeModels((prev) => prev.map((entry) => {
      if (String(entry.id) !== nodeId) return entry;
      const outputs = Array.isArray(entry.outputs) ? entry.outputs : [];
      return normalizeNodeModel({
        ...entry,
        outputs: outputs.filter((out: any) => String(out?.id || '') !== normalizedOutputId),
      });
    }));
    setEdgeModels((prev) => prev.filter((edge) =>
      !(String(edge.source) === nodeId && String(edge.sourceOutput || '') === normalizedOutputId),
    ));
    setConnectSourceOutput((prev) => (prev === normalizedOutputId ? '' : prev));
    emitWorkflowAction('workflow_remove_conditional_output', { nodeId, outputId: normalizedOutputId });
  }, [emitWorkflowAction, selectedNode]);

  const addConditionalOutput = React.useCallback(() => {
    if (!selectedNode || !isEvaluatorSelected) return;
    const nodeId = String(selectedNode.id || '');
    const outputId = String(newOutputId || '').trim();
    if (!nodeId || !outputId) return;

    const mode = String(newOutputMode || 'AND').trim() || 'AND';
    const conditions = newOutputConditions
      .map((entry) => ({
        value1: String(entry.value1 || '').trim(),
        operator: String(entry.operator || '==').trim() || '==',
        value2: String(entry.value2 || '').trim(),
      }))
      .filter((entry) => entry.value1 && entry.value2);
    if (conditions.length === 0) return;

    const conditionLabel = conditions.map((entry) => `${entry.value1} ${entry.operator} ${entry.value2}`).join(` ${mode} `);
    const label = `${outputId} (${conditionLabel})`;
    const params = Array.from(new Set(conditions.flatMap((entry) => [entry.value1, entry.value2]).filter(Boolean)));

    setNodeModels((prev) => prev.map((entry) => {
      if (String(entry.id) !== nodeId) return entry;
      const existing = Array.isArray(entry.outputs) ? entry.outputs : [];
      if (existing.some((out) => String(out.id || '') === outputId)) return entry;
      return normalizeNodeModel({
        ...entry,
        outputs: [...existing, { id: outputId, label, params, conditionMode: mode, conditions }],
      });
    }));
    setNewOutputId('');
    setNewOutputMode('AND');
    setNewOutputConditions([createConditionDraft()]);
    emitWorkflowAction('workflow_add_conditional_output', {
      nodeId,
      outputId,
      mode,
      conditions,
    });
  }, [
    emitWorkflowAction,
    isEvaluatorSelected,
    newOutputId,
    newOutputConditions,
    newOutputMode,
    selectedNode,
  ]);

  React.useEffect(() => {
    if (!rfInstance || uiNodes.length === 0) return;
    const handle = window.requestAnimationFrame(() => {
      rfInstance.fitView({ duration: 0, padding: 0.2 });
    });
    return () => window.cancelAnimationFrame(handle);
  }, [rfInstance, uiNodes.length]);

  const selectedConfigJson = React.useMemo(() => {
    if (!selectedNode) return '{}';
    try {
      return JSON.stringify(selectedNode.config || {}, null, 2);
    } catch {
      return '{}';
    }
  }, [selectedNode]);

  const selectedEdgeMappingJson = React.useMemo(() => {
    if (!selectedEdge) return '{}';
    try {
      return JSON.stringify(selectedEdge.mapping || {}, null, 2);
    } catch {
      return '{}';
    }
  }, [selectedEdge]);

  return (
    <Card className="w-full max-w-none" style={parseStyle(style)}>
      {title ? (
        <CardHeader>
          <CardTitle className="text-sm">{getLiteral(title)}</CardTitle>
        </CardHeader>
      ) : null}
      <CardContent className="space-y-3">
        <div className="flex flex-wrap items-center gap-2 rounded-md border bg-card/60 p-2">
          <Button size="sm" onClick={() => setIsAddModalOpen(true)}>Add Component</Button>
          <Button size="sm" variant="outline" onClick={applyAutoLayout}>Auto Layout</Button>
          <Button size="sm" variant="outline" onClick={fitCanvas}>Fit</Button>
        </div>

        <div className="grid min-h-0 gap-3">
          <div
            className="ui-data-panel ui-workflow-shell relative min-w-0 w-full rounded-md border"
            style={{ height: Math.max(260, Number(height) || 560) }}
          >
            <div className="ui-workflow-badge pointer-events-none absolute right-2 top-2 z-20 rounded px-2 py-0.5 font-mono text-[10px] ui-workflow-badge-text">
              nodes {uiNodes.length} | edges {rfEdges.length}
            </div>
            <div className="ui-workflow-badge pointer-events-none absolute left-2 top-2 z-20 rounded px-2 py-0.5 font-mono text-[10px] ui-workflow-badge-text">
              edge valid {edgeDiagnostics.valid}/{edgeDiagnostics.total} | invalid {edgeDiagnostics.invalid}
            </div>
            {uiNodes.length === 0 ? (
              <div className="flex h-full items-center justify-center text-sm text-muted-foreground">No workflow nodes</div>
            ) : (
              <ReactFlow
                className="h-full w-full"
                nodeTypes={WORKFLOW_NODE_TYPES}
                nodes={uiNodes}
                edges={rfEdges}
                onNodesChange={onNodesChange}
                onNodeDragStop={onNodeDragStop}
                onEdgesChange={onEdgesChange}
                onConnect={onConnect}
                onInit={(instance) => {
                  setRfInstance(instance as any);
                  window.requestAnimationFrame(() => {
                    instance.fitView({ duration: 0, padding: 0.2 });
                  });
                }}
                onNodeClick={(_, node) => {
                  const nodeId = String(node.id || '');
                  setSelectedNodeId(nodeId);
                  setSelectedEdgeId('');
                  emitWorkflowAction('workflow_select_node', { nodeId });
                }}
                onEdgeClick={(_, edge) => {
                  const edgeId = String(edge.id || '');
                  setSelectedEdgeId(edgeId);
                  setSelectedNodeId('');
                  emitWorkflowAction('workflow_select_edge', { edgeId });
                }}
                onPaneClick={() => {
                  setSelectedNodeId('');
                  setSelectedEdgeId('');
                  setIsSelectionDrawerOpen(false);
                }}
                connectionMode={ConnectionMode.Strict}
                isValidConnection={(connection) =>
                  Boolean(connection.source) &&
                  Boolean(connection.target) &&
                  connection.source !== connection.target &&
                  connection.sourceHandle !== 'in' &&
                  (connection.targetHandle === 'in' || !connection.targetHandle)
                }
                fitView
                fitViewOptions={{ padding: 0.2 }}
                nodesDraggable
                nodesConnectable
                elementsSelectable
                proOptions={{ hideAttribution: true }}
              >
                <Background gap={18} size={1} color={DATA_THEME.surface.border} />
              </ReactFlow>
            )}
          </div>
          {!selectedNode && !selectedEdge ? (
            <div className="w-full rounded-md border bg-card/60 p-3 text-sm text-muted-foreground">
              Select a node or connection to inspect details.
            </div>
          ) : null}
        </div>

        <Dialog open={isAddModalOpen} onOpenChange={setIsAddModalOpen}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Add Workflow Element</DialogTitle>
              <DialogDescription>Select a template to add a new node in the workflow canvas.</DialogDescription>
            </DialogHeader>
            <Tabs value={activeTemplateTab} onValueChange={(value) => setActiveTemplateTab(value as TemplateTab)}>
              <TabsList className="grid w-full grid-cols-3">
                <TabsTrigger value="triggers">Triggers</TabsTrigger>
                <TabsTrigger value="components">Components</TabsTrigger>
                <TabsTrigger value="pipelines">Pipelines</TabsTrigger>
              </TabsList>

              <TabsContent value="triggers" className="mt-3 space-y-2">
                <Label className="text-[11px] uppercase tracking-wide text-muted-foreground">Trigger</Label>
                {templatesByTab.triggers.length > 0 ? (
                  <Select
                    value={selectedTemplateByTab.triggers}
                    onValueChange={(value) => setSelectedTemplateByTab((prev) => ({ ...prev, triggers: value }))}
                  >
                    <SelectTrigger>
                      <SelectValue placeholder="Select trigger" />
                    </SelectTrigger>
                    <SelectContent>
                      {templatesByTab.triggers.map((entry) => (
                        <SelectItem key={entry.id} value={entry.id}>
                          {entry.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                ) : (
                  <p className="text-sm text-muted-foreground">No triggers available.</p>
                )}
              </TabsContent>

              <TabsContent value="components" className="mt-3 space-y-2">
                <Label className="text-[11px] uppercase tracking-wide text-muted-foreground">Component</Label>
                {templatesByTab.components.length > 0 ? (
                  <Select
                    value={selectedTemplateByTab.components}
                    onValueChange={(value) => setSelectedTemplateByTab((prev) => ({ ...prev, components: value }))}
                  >
                    <SelectTrigger>
                      <SelectValue placeholder="Select component" />
                    </SelectTrigger>
                    <SelectContent>
                      {templatesByTab.components.map((entry) => (
                        <SelectItem key={entry.id} value={entry.id}>
                          {entry.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                ) : (
                  <p className="text-sm text-muted-foreground">No components available.</p>
                )}
              </TabsContent>

              <TabsContent value="pipelines" className="mt-3 space-y-2">
                <Label className="text-[11px] uppercase tracking-wide text-muted-foreground">Pipeline</Label>
                {templatesByTab.pipelines.length > 0 ? (
                  <Select
                    value={selectedTemplateByTab.pipelines}
                    onValueChange={(value) => setSelectedTemplateByTab((prev) => ({ ...prev, pipelines: value }))}
                  >
                    <SelectTrigger>
                      <SelectValue placeholder="Select pipeline" />
                    </SelectTrigger>
                    <SelectContent>
                      {templatesByTab.pipelines.map((entry) => (
                        <SelectItem key={entry.id} value={entry.id}>
                          {entry.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                ) : (
                  <p className="text-sm text-muted-foreground">No pipelines available.</p>
                )}
              </TabsContent>
            </Tabs>
            <DialogFooter>
              <Button variant="outline" onClick={() => setIsAddModalOpen(false)}>Cancel</Button>
              <Button
                onClick={() => addNodeFromTemplate(selectedTemplateByTab[activeTemplateTab])}
                disabled={!selectedTemplateByTab[activeTemplateTab]}
              >
                Add
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>

        <Sheet
          open={isSelectionDrawerOpen}
          onOpenChange={(open) => {
            setIsSelectionDrawerOpen(open);
            if (!open) {
              setSelectedNodeId('');
              setSelectedEdgeId('');
            }
          }}
        >
          <SheetContent side="right" className="w-[min(420px,96vw)] overflow-y-auto">
            <SheetHeader>
              <SheetTitle>Selection</SheetTitle>
            </SheetHeader>
            <div className="mt-4 grid gap-3">
              {selectedNode ? (
                <div className="grid gap-2">
                  <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Node</p>
                  <p className="text-sm"><span className="text-muted-foreground">ID:</span> {String(selectedNode.id || '-')}</p>
                  <p className="text-sm"><span className="text-muted-foreground">Type:</span> {String(selectedNode.nodeType || '-')}</p>
                  <p className="text-sm"><span className="text-muted-foreground">Status:</span> {String(selectedNode.status || '-')}</p>
                  <p className="text-sm"><span className="text-muted-foreground">I/O:</span> {selectedNode.input?.params?.length || 0} in / {selectedNode.outputs?.length || 0} out</p>
                  <Label className="mt-1 text-[11px] uppercase tracking-wide text-muted-foreground">Config</Label>
                  <Textarea readOnly value={selectedConfigJson} className="min-h-28 font-mono text-xs" />

                  <Label className="mt-2 text-[11px] uppercase tracking-wide text-muted-foreground">Create Connection</Label>
                  <Select value={connectSourceOutput} onValueChange={setConnectSourceOutput} disabled={connectSourceOptions.length === 0}>
                    <SelectTrigger>
                      <SelectValue placeholder="Select source output" />
                    </SelectTrigger>
                    <SelectContent>
                      {connectSourceOptions.map((entry) => (
                        <SelectItem key={entry.value} value={entry.value}>
                          {entry.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <Select value={connectTargetNodeId} onValueChange={setConnectTargetNodeId} disabled={connectTargetOptions.length === 0}>
                    <SelectTrigger>
                      <SelectValue placeholder="Select target node" />
                    </SelectTrigger>
                    <SelectContent>
                      {connectTargetOptions.map((entry) => (
                        <SelectItem key={entry.value} value={entry.value}>
                          {entry.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={connectSelectedOutput}
                    disabled={!connectSourceOutput || !connectTargetNodeId}
                  >
                    Connect Output
                  </Button>

                  <Label className="mt-2 text-[11px] uppercase tracking-wide text-muted-foreground">Conditional Outputs (Evaluator)</Label>
                  {isEvaluatorSelected && Array.isArray(selectedNode.outputs) && selectedNode.outputs.length > 0 ? (
                    <div className="grid gap-1 rounded-md border p-2">
                      {selectedNode.outputs
                        .filter((out: any) => Array.isArray(out?.conditions) && out.conditions.length > 0)
                        .map((out: any) => (
                          <div key={String(out.id)} className="flex items-center justify-between gap-2 rounded border px-2 py-1">
                            <span className="truncate text-xs">{String(out.label || out.id || '')}</span>
                            <Button
                              type="button"
                              variant="outline"
                              size="sm"
                              onClick={() => removeConditionalOutput(String(out.id || ''))}
                            >
                              Remove
                            </Button>
                          </div>
                        ))}
                    </div>
                  ) : null}
                  <Input
                    value={newOutputId}
                    onChange={(event) => setNewOutputId(event.target.value)}
                    placeholder="Output id (e.g. high_priority)"
                    disabled={!isEvaluatorSelected}
                  />
                  <Select value={newOutputMode} onValueChange={setNewOutputMode} disabled={!isEvaluatorSelected}>
                    <SelectTrigger>
                      <SelectValue placeholder="Mode" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="AND">AND</SelectItem>
                      <SelectItem value="OR">OR</SelectItem>
                    </SelectContent>
                  </Select>
                  <div className="grid gap-2 rounded-md border p-2">
                    {newOutputConditions.map((condition, idx) => (
                      <div key={condition.id} className="grid gap-2 rounded border p-2">
                        <p className="text-[11px] uppercase tracking-wide text-muted-foreground">Condition {idx + 1}</p>
                        <Input
                          value={condition.value1}
                          onChange={(event) => updateConditionRow(condition.id, 'value1', event.target.value)}
                          placeholder="Value 1 (e.g. payload.score)"
                          disabled={!isEvaluatorSelected}
                        />
                        <Select
                          value={condition.operator}
                          onValueChange={(value) => updateConditionRow(condition.id, 'operator', value)}
                          disabled={!isEvaluatorSelected}
                        >
                          <SelectTrigger>
                            <SelectValue placeholder="Operator" />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="==">==</SelectItem>
                            <SelectItem value="!=">!=</SelectItem>
                            <SelectItem value=">">&gt;</SelectItem>
                            <SelectItem value="<">&lt;</SelectItem>
                            <SelectItem value=">=">&gt;=</SelectItem>
                            <SelectItem value="<=">&lt;=</SelectItem>
                            <SelectItem value="in">in</SelectItem>
                            <SelectItem value="contains">contains</SelectItem>
                          </SelectContent>
                        </Select>
                        <Input
                          value={condition.value2}
                          onChange={(event) => updateConditionRow(condition.id, 'value2', event.target.value)}
                          placeholder="Value 2 (e.g. 80)"
                          disabled={!isEvaluatorSelected}
                        />
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => removeConditionRow(condition.id)}
                          disabled={!isEvaluatorSelected || newOutputConditions.length <= 1}
                        >
                          Remove Condition
                        </Button>
                      </div>
                    ))}
                    <Button variant="outline" size="sm" onClick={addConditionRow} disabled={!isEvaluatorSelected}>
                      Add Condition
                    </Button>
                  </div>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={addConditionalOutput}
                    disabled={!isEvaluatorSelected || !newOutputId.trim()}
                  >
                    Add Conditional Output
                  </Button>

                  <Button variant="destructive" size="sm" onClick={deleteSelectedNode}>Delete Node</Button>
                </div>
              ) : null}

              {selectedEdge ? (
                <div className={cn('grid gap-2', selectedNode ? 'border-t pt-3' : '')}>
                  <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Connection</p>
                  <p className="text-sm"><span className="text-muted-foreground">From:</span> {String(selectedEdge.source || '-')}</p>
                  <p className="text-sm"><span className="text-muted-foreground">To:</span> {String(selectedEdge.target || '-')}</p>
                  <p className="text-sm"><span className="text-muted-foreground">Output:</span> {String(selectedEdge.sourceOutput || '-')}</p>
                  <Label className="mt-1 text-[11px] uppercase tracking-wide text-muted-foreground">Edge Param Mapping</Label>
                  <Textarea
                    value={edgeMappingDraft}
                    onChange={(event) => setEdgeMappingDraft(event.target.value)}
                    className="min-h-28 font-mono text-xs"
                    placeholder='{"target_param":"source_param"}'
                  />
                  <Button variant="outline" size="sm" onClick={applyEdgeMapping}>Apply Mapping</Button>
                  <Button variant="destructive" size="sm" onClick={deleteSelectedEdge}>Delete Connection</Button>
                </div>
              ) : null}
            </div>
          </SheetContent>
        </Sheet>
      </CardContent>
    </Card>
  );
};
