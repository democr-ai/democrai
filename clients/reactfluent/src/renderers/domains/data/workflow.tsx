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
import { 
  Button, 
  Card, 
  CardBody, 
  CardHeader, 
  CardTitle,
  Modal,
  ModalHeader,
  ModalBody,
  ModalFooter,
  Input,
  Select,
  Nav,
  NavItem,
  NavLink,
  TabContent,
  TabPane
} from 'design-react-kit';
import { Offcanvas, OffcanvasHeader, OffcanvasBody } from 'reactstrap';
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
      className="position-relative border rounded p-2 shadow-sm"
      style={{
        minWidth: '180px',
        borderColor: stroke,
        background: fill,
        color: textColor,
        boxShadow: selected ? '0 0 0 3px var(--bs-primary-bg-subtle)' : '0 2px 4px rgba(0,0,0,0.05)',
      }}
    >
      <Handle id="in" type="target" position={Position.Left} style={{ width: '10px', height: '10px', background: '#fff', border: `2px solid ${stroke}` }} />
      <div className="text-truncate small fw-bold">{String(data?.label || 'Nodo')}</div>
      <div className="text-truncate xsmall opacity-75">{String(data?.nodeType || 'componente')}</div>
      <div className="text-truncate xsmall opacity-50">{String(data?.status || 'pronto')}</div>

      {outputs.length === 0 && (
        <Handle id="out" type="source" isConnectable={true} position={Position.Right} style={{ width: '10px', height: '10px', background: stroke, border: '2px solid #fff' }} />
      )}

      {outputs.length > 0 && (
        <div className="mt-2 d-flex flex-column gap-1">
          {outputs.map((out, idx) => {
            const top = `${((idx + 1) * 100) / (outputs.length + 1)}%`;
            return (
              <div key={out.id} className="position-relative d-flex justify-content-end align-items-center">
                <span className="pe-2 xsmall fw-bold opacity-75 text-uppercase" style={{ fontSize: '9px' }}>{out.label}</span>
                <Handle
                  id={String(out.id)}
                  type="source"
                  position={Position.Right}
                  style={{ top, width: '10px', height: '10px', background: stroke, border: '2px solid #fff' }}
                />
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};

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
    label: 'Trigger Webhook',
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
    label: 'Bonifica Input',
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
    label: 'Classificatore Priorità',
    nodeType: 'ai',
    status: 'ready',
    fill: WORKFLOW_THEME.nodeFill,
    stroke: dataStatusColor('success', WORKFLOW_THEME.nodeStroke),
    textColor: WORKFLOW_THEME.nodeText,
    x: 640,
    y: 180,
    input: { params: ['email', 'subject', 'priority'] },
    outputs: [
      { id: 'high', label: 'alta', params: ['ticket_id', 'priority', 'email'] },
      { id: 'normal', label: 'normale', params: ['ticket_id', 'priority', 'email'] },
    ],
  },
];

const DEFAULT_FLOW_EDGES: WorkflowEdgeLike[] = [
  { source: 'webhook', target: 'sanitize', sourceOutput: 'payload', label: 'payload' },
  { source: 'sanitize', target: 'classifier', sourceOutput: 'normalized', label: 'normalized' },
];

const coerceColor = (value: any, fallback: string): string => String(value || '').trim() || fallback;
const gridPosition = (index: number) => ({ x: 80 + ((index % 4) * 280), y: 50 + (Math.floor(index / 4) * 200) });
const toFiniteNumber = (value: any, fallback: number): number => {
  const n = typeof value === 'number' ? value : Number.parseFloat(String(value || ''));
  return Number.isFinite(n) ? n : fallback;
};
const normalizeCanvasCoord = (value: number, fallback: number): number => (Number.isFinite(value) && Math.abs(value) < 10000) ? value : fallback;
const endpointToId = (value: any): string => {
  if (typeof value === 'string' || typeof value === 'number') return String(value).trim();
  return value && typeof value === 'object' ? String(value.id ?? value.nodeId ?? value.node ?? value.key ?? value.name ?? '').trim() : '';
};
const outputHandleToId = (value: any): string => {
  if (typeof value === 'string' || typeof value === 'number') return String(value).trim();
  return value && typeof value === 'object' ? String(value.id ?? value.output ?? value.name ?? '').trim() : '';
};
const stableSerialize = (v: any) => JSON.stringify(v || {});
const createConditionDraft = (): ConditionDraft => ({ id: `cond_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`, value1: '', operator: '==', value2: '' });

const normalizeTemplates = (raw: any[]): NodeTemplate[] => {
  if (!Array.isArray(raw)) return [];
  return raw.map((entry, index) => {
    if (!entry || typeof entry !== 'object') return null;
    const id = String(entry.id || `template_${index + 1}`).trim();
    const outputs = Array.isArray(entry.outputs) ? entry.outputs.map((out: any, oIdx: number) => {
      const oid = String(out?.id || `out_${oIdx + 1}`).trim();
      return { id: oid, label: getLiteral(out?.label || oid), params: Array.isArray(out?.params) ? out.params.map((v: any) => String(v || '').trim()) : [] };
    }) : [{ id: 'out_1', label: 'out_1', params: [] }];
    return {
      id,
      label: getLiteral(entry.label || id),
      nodeType: String(entry.nodeType || entry.type || 'component').trim(),
      status: String(entry.status || 'ready').toLowerCase(),
      fill: coerceColor(entry.fill, WORKFLOW_THEME.nodeFill),
      stroke: coerceColor(entry.stroke, WORKFLOW_THEME.nodeStroke),
      textColor: coerceColor(entry.textColor, WORKFLOW_THEME.nodeText),
      config: entry.config || {},
      input: { params: Array.isArray(entry.input?.params) ? entry.input.params : [] },
      outputs,
      allowAddOutput: toBoolean(entry.allowAddOutput ?? true),
    };
  }).filter(Boolean) as NodeTemplate[];
};

const normalizeNodeModel = (node: WorkflowNodeLike): WorkflowNodeLike => ({
  ...node,
  id: String(node?.id || ''),
  label: getLiteral(node?.label || node?.id || 'Nodo'),
  nodeType: String(node?.nodeType || 'component'),
  status: String(node?.status || 'ready').toLowerCase(),
  fill: coerceColor(node?.fill, WORKFLOW_THEME.nodeFill),
  stroke: coerceColor(node?.stroke, WORKFLOW_THEME.nodeStroke),
  textColor: coerceColor(node?.textColor, WORKFLOW_THEME.nodeText),
  config: node?.config || {},
  input: { params: Array.isArray(node?.input?.params) ? node.input!.params : [] },
  outputs: Array.isArray(node?.outputs) ? node.outputs.map((out: any, idx: number) => ({
    id: String(out?.id || `out_${idx + 1}`),
    label: getLiteral(out?.label || out?.id || `out_${idx + 1}`),
    params: Array.isArray(out?.params) ? out.params : [],
    conditionMode: String(out?.conditionMode || 'AND'),
    conditions: Array.isArray(out?.conditions) ? out.conditions.map((e: any) => ({ value1: String(e?.value1 || '').trim(), operator: String(e?.operator || '==').trim(), value2: String(e?.value2 || '').trim() })).filter(e => e.value1 || e.value2) : []
  })) : [{ id: 'out_1', label: 'out_1', params: [] }],
  allowAddOutput: toBoolean(node?.allowAddOutput ?? true),
});

const normalizeEdgeModel = (edge: WorkflowEdgeLike, index: number): WorkflowEdgeLike | null => {
  const source = endpointToId(edge?.source || edge?.from);
  const target = endpointToId(edge?.target || edge?.to);
  if (!source || !target) return null;
  const sourceOutput = outputHandleToId(edge?.sourceOutput);
  return { ...edge, id: String(edge?.id || `edge_${source}_${target}_${sourceOutput || 'default'}`), source, target, label: getLiteral(edge?.label || sourceOutput), sourceOutput, mapping: edge?.mapping || {} };
};

const sanitizeNodeModels = (raw: WorkflowNodeLike[]): WorkflowNodeLike[] => {
  const seen = new Set<string>();
  return raw.map((entry, idx) => {
    let id = String(entry?.id || `node_${idx + 1}`).trim();
    if (seen.has(id)) id = `${id}_${idx + 1}`;
    seen.add(id);
    return normalizeNodeModel({ ...entry, id });
  });
};

const mapNodeToRF = (node: WorkflowNodeLike, index: number, w: number, h: number): Node<WorkflowNodeData> => {
  const fallback = gridPosition(index);
  const x = normalizeCanvasCoord(toFiniteNumber(node.position?.x ?? node.x, fallback.x), fallback.x);
  const y = normalizeCanvasCoord(toFiniteNumber(node.position?.y ?? node.y, fallback.y), fallback.y);
  return {
    id: String(node.id),
    type: 'workflowNode',
    data: { label: getLiteral(node.label || node.id), nodeType: String(node.nodeType), status: String(node.status), stroke: String(node.stroke), fill: String(node.fill), textColor: String(node.textColor), outputs: node.outputs },
    position: { x, y },
    sourcePosition: Position.Right,
    targetPosition: Position.Left,
    width: Math.max(160, w),
    height: Math.max(80, h + (node.outputs?.length || 0) * 16),
    draggable: true,
    selectable: true,
  };
};

const mapEdgeToRF = (edge: WorkflowEdgeLike): Edge => ({
  id: String(edge.id),
  source: String(edge.source),
  target: String(edge.target),
  sourceHandle: String(edge.sourceOutput || 'out'),
  targetHandle: 'in',
  markerEnd: { type: MarkerType.ArrowClosed, color: WORKFLOW_THEME.nodeStroke },
  style: { stroke: WORKFLOW_THEME.nodeStroke, strokeWidth: 2 }
});

export const Workflow: React.FC<any> = ({ title, nodes = [], edges = [], triggers = [], components = [], pipelines = [], componentCatalog = [], style, height = 560, nodeWidth = 200, nodeHeight = 90, onAction, emitActionEvents = false }) => {
  const [rfInstance, setRfInstance] = React.useState<ReactFlowInstance | null>(null);
  const emit = React.useCallback((n: string, p: any) => emitActionEvents && onAction?.(n, p), [emitActionEvents, onAction]);

  const initialNodes = React.useMemo(() => sanitizeNodeModels((Array.isArray(nodes) ? nodes : Object.values(nodes || {})).map(n => normalizeNodeModel(n))), [nodes]);
  const initialEdges = React.useMemo(() => {
    const raw = Array.isArray(edges) ? edges : Object.values(edges || {});
    return raw.map((e, i) => normalizeEdgeModel(e, i)).filter(Boolean) as WorkflowEdgeLike[];
  }, [edges]);

  const [nodeModels, setNodeModels] = React.useState(initialNodes);
  const [edgeModels, setEdgeModels] = React.useState(initialEdges);
  const [selectedNodeId, setSelectedNodeId] = React.useState('');
  const [selectedEdgeId, setSelectedEdgeId] = React.useState('');
  const [activeTab, setActiveTab] = React.useState<TemplateTab>('components');
  const [showAdd, setShowAdd] = React.useState(false);
  const [showDrawer, setShowDrawer] = React.useState(false);
  const [mappingDraft, setMappingDraft] = React.useState('');
  const [connOut, setConnOut] = React.useState('');
  const [connTarget, setConnTarget] = React.useState('');
  const [newOutId, setNewOutId] = React.useState('');
  const [newOutMode, setNewOutMode] = React.useState('AND');
  const [newOutConds, setNewOutConds] = React.useState([createConditionDraft()]);

  React.useEffect(() => { setNodeModels(initialNodes); }, [initialNodes]);
  React.useEffect(() => { setEdgeModels(initialEdges); }, [initialEdges]);

  const templates = React.useMemo(() => ({
    triggers: normalizeTemplates(triggers),
    components: normalizeTemplates([...components, ...componentCatalog]),
    pipelines: normalizeTemplates(pipelines)
  }), [triggers, components, componentCatalog, pipelines]);

  const selectedNode = nodeModels.find(n => n.id === selectedNodeId);
  const selectedEdge = edgeModels.find(e => e.id === selectedEdgeId);

  const uiNodes = React.useMemo(() => nodeModels.map((n, i) => mapNodeToRF(n, i, nodeWidth, nodeHeight)), [nodeModels, nodeWidth, nodeHeight]);
  const rfEdges = React.useMemo(() => edgeModels.map(mapEdgeToRF), [edgeModels]);

  const onNodesChange = React.useCallback((chs: NodeChange<Node>[]) => {
    setNodeModels(prev => {
      const next = applyNodeChanges(chs, prev.map((n, i) => mapNodeToRF(n, i, 0, 0)) as any) as any[];
      return next.map(n => {
        const orig = prev.find(p => p.id === n.id);
        return normalizeNodeModel({ ...orig, x: n.position.x, y: n.position.y, position: n.position });
      });
    });
  }, []);

  const onEdgesChange = React.useCallback((chs: EdgeChange<Edge>[]) => {
    setEdgeModels(prev => {
      const next = applyEdgeChanges(chs, prev.map(mapEdgeToRF));
      return next.map((e, i) => normalizeEdgeModel({ id: e.id, source: e.source, target: e.target, sourceOutput: (e as any).sourceHandle }, i)).filter(Boolean) as any[];
    });
  }, []);

  const onConnect = React.useCallback((p: any) => {
    if (!p.source || !p.target || p.source === p.target) return;
    setEdgeModels(prev => {
      const next = addEdge({ ...p, sourceHandle: p.sourceHandle || 'out', targetHandle: 'in' }, prev.map(mapEdgeToRF));
      return next.map((e, i) => normalizeEdgeModel({ id: e.id, source: e.source, target: e.target, sourceOutput: (e as any).sourceHandle }, i)).filter(Boolean) as any[];
    });
  }, []);

  const addNode = (tid: string) => {
    const t = [...templates.triggers, ...templates.components, ...templates.pipelines].find(x => x.id === tid);
    if (!t) return;
    const pos = gridPosition(nodeModels.length);
    const n = normalizeNodeModel({ ...t, id: `${t.id}_${Date.now()}`, x: pos.x, y: pos.y });
    setNodeModels(p => [...p, n]);
    setShowAdd(false);
    emit('workflow_add_node', { node: n });
  };

  return (
    <Card style={parseStyle(style)} className="border shadow-sm">
      {title && (
        <CardHeader className="bg-light border-bottom py-2">
          <CardTitle className="m-0 xsmall text-uppercase fw-bold text-muted">{getLiteral(title)}</CardTitle>
        </CardHeader>
      )}
      <CardBody className="p-3">
        <div className="d-flex gap-2 mb-3 bg-light p-2 rounded border">
          <Button color="primary" size="sm" onClick={() => setShowAdd(true)}>
            <i className="ri-add-line me-1" /> Add Component
          </Button>
          <Button color="primary" outline size="sm" onClick={() => rfInstance?.fitView({ duration: 200 })}>
            <i className="ri-focus-3-line me-1" /> Fit
          </Button>
        </div>

        <div className="border rounded bg-light overflow-hidden position-relative" style={{ height: Math.max(300, Number(height) || 560) }}>
          <div className="position-absolute top-0 end-0 m-2 z-index-10 bg-white border rounded px-2 py-1 xsmall font-monospace opacity-75">
            nodes: {nodeModels.length} | edges: {edgeModels.length}
          </div>
          <ReactFlow
            nodes={uiNodes}
            edges={rfEdges}
            nodeTypes={WORKFLOW_NODE_TYPES}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={onConnect}
            onInit={setRfInstance}
            onNodeClick={(_, n) => { setSelectedNodeId(n.id); setSelectedEdgeId(''); setShowDrawer(true); }}
            onEdgeClick={(_, e) => { setSelectedEdgeId(e.id); setSelectedNodeId(''); setShowDrawer(true); }}
            onPaneClick={() => { setSelectedNodeId(''); setSelectedEdgeId(''); setShowDrawer(false); }}
            connectionMode={ConnectionMode.Strict}
            fitView
          >
            <Background gap={20} color="#e9ecef" />
          </ReactFlow>
        </div>

        <Modal isOpen={showAdd} toggle={() => setShowAdd(!showAdd)} centered>
          <ModalHeader toggle={() => setShowAdd(false)}>Add Workflow Item</ModalHeader>
          <ModalBody>
            <Nav tabs className="mb-3">
              {(['triggers', 'components', 'pipelines'] as const).map(t => (
                <NavItem key={t}>
                  <NavLink className={cn("cursor-pointer", activeTab === t && "active")} onClick={() => setActiveTab(t)}>
                    {t === 'triggers' ? 'Trigger' : t === 'components' ? 'Componenti' : 'Pipeline'}
                  </NavLink>
                </NavItem>
              ))}
            </Nav>
            <TabContent activeTab={activeTab}>
              {templates[activeTab].length > 0 ? (
                <div className="list-group">
                  {templates[activeTab].map(t => (
                    <button key={t.id} className="list-group-item list-group-item-action d-flex justify-content-between align-items-center" onClick={() => addNode(t.id)}>
                      <span className="small fw-bold">{t.label}</span>
                      <i className="ri-add-circle-line text-primary fs-5" />
                    </button>
                  ))}
                </div>
              ) : (
                <p className="text-center text-muted p-4 small">Nessun elemento disponibile in questa categoria.</p>
              )}
            </TabContent>
          </ModalBody>
        </Modal>

        <Offcanvas isOpen={showDrawer} toggle={() => setShowDrawer(!showDrawer)} direction="end" style={{ width: '400px' }}>
          <OffcanvasHeader toggle={() => setShowDrawer(false)}>
            {selectedNode ? 'Dettagli Nodo' : 'Dettagli Connessione'}
          </OffcanvasHeader>
          <OffcanvasBody className="small">
            {selectedNode && (
              <div className="d-flex flex-column gap-3">
                <div className="p-3 bg-light border rounded">
                  <div className="mb-1 text-uppercase xsmall fw-bold text-muted">ID Nodo</div>
                  <div className="font-monospace mb-2">{selectedNode.id}</div>
                  <div className="mb-1 text-uppercase xsmall fw-bold text-muted">Type</div>
                  <div>{selectedNode.nodeType}</div>
                </div>
                
                <div>
                  <Input type="textarea" tag="textarea" readOnly value={JSON.stringify(selectedNode.config, null, 2)} style={{ height: '150px', fontSize: '11px', fontFamily: 'monospace' }} />
                </div>

                <Button color="danger" outline size="sm" className="mt-4" onClick={() => { setNodeModels(p => p.filter(x => x.id !== selectedNode.id)); setShowDrawer(false); }}>
                  <i className="ri-delete-bin-line me-1" /> Delete Node
                </Button>
              </div>
            )}

            {selectedEdge && (
              <div className="d-flex flex-column gap-3">
                <div className="p-3 bg-light border rounded">
                  <div className="mb-2">
                    <span className="xsmall fw-bold text-uppercase text-muted d-block">Source</span>
                    <span className="font-monospace">{selectedEdge.source} ({selectedEdge.sourceOutput})</span>
                  </div>
                  <div>
                    <span className="xsmall fw-bold text-uppercase text-muted d-block">Target</span>
                    <span className="font-monospace">{selectedEdge.target}</span>
                  </div>
                </div>

                <Button color="danger" outline size="sm" className="mt-4" onClick={() => { setEdgeModels(p => p.filter(x => x.id !== selectedEdge.id)); setShowDrawer(false); }}>
                  <i className="ri-delete-bin-line me-1" /> Delete Connection
                </Button>
              </div>
            )}
          </OffcanvasBody>
        </Offcanvas>
      </CardBody>
    </Card>
  );
};
