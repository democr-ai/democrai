import React from 'react';
import { parseStyle } from '@/utils/style';
import { getLiteral } from '@/renderers/shared';
import { DATA_THEME } from '@/utils/dataTheme';

type SequenceParticipant = { id: string; label: string };
type SequenceMessage = { source: string; target: string; text: string; type: string };

type SequenceModel = {
  participants: SequenceParticipant[];
  messages: SequenceMessage[];
};

const PARTICIPANT_RE = /^(?:participant|actor)\s+([A-Za-z0-9_.-]+)(?:\s+as\s+(.+))?$/i;
const MESSAGE_RE = /^([A-Za-z0-9_.-]+)\s*(-->>|->>|-->|->|--x|-x|==>>|=>>|==>|=>)\s*([A-Za-z0-9_.-]+)\s*:\s*(.+)$/;

const parseMermaid = (raw: string): SequenceModel => {
  const text = String(raw || '').trim();
  if (!text) return { participants: [], messages: [] };
  const lines = text.split('\n').map((line) => line.trim()).filter((line) => line && !line.startsWith('%%'));
  if (!lines.length || lines[0].toLowerCase() !== 'sequencediagram') return { participants: [], messages: [] };
  const participants = new Map<string, SequenceParticipant>();
  const messages: SequenceMessage[] = [];
  for (const line of lines.slice(1)) {
    const lower = line.toLowerCase();
    if (lower.startsWith('autonumber') || lower.startsWith('note ') || lower.startsWith('activate ') || lower.startsWith('deactivate ') || lower.startsWith('loop ') || lower.startsWith('alt ') || lower.startsWith('opt ') || lower.startsWith('par ') || lower.startsWith('and ') || lower === 'else' || lower === 'end') continue;
    const part = line.match(PARTICIPANT_RE);
    if (part) {
      const id = String(part[1] || '').trim();
      if (!id) continue;
      participants.set(id, { id, label: String(part[2] || id).trim() || id });
      continue;
    }
    const msg = line.match(MESSAGE_RE);
    if (!msg) continue;
    const source = String(msg[1] || '').trim(), arrow = String(msg[2] || '').trim(), target = String(msg[3] || '').trim(), textValue = String(msg[4] || '').trim();
    if (!source || !target) continue;
    if (!participants.has(source)) participants.set(source, { id: source, label: source });
    if (!participants.has(target)) participants.set(target, { id: target, label: target });
    messages.push({ source, target, text: textValue, type: arrow.startsWith('--') || arrow.startsWith('==') ? 'reply' : 'sync' });
  }
  return { participants: Array.from(participants.values()), messages };
};

const normalizeModel = (participantsRaw: any, messagesRaw: any, mermaid: any): SequenceModel => {
  const participantsArray = Array.isArray(participantsRaw) ? participantsRaw : [];
  const messagesArray = Array.isArray(messagesRaw) ? messagesRaw : [];
  if (!participantsArray.length && !messagesArray.length) return parseMermaid(getLiteral(mermaid));
  const participants = new Map<string, SequenceParticipant>();
  const messages: SequenceMessage[] = [];
  participantsArray.forEach((entry: any, idx: number) => {
    const id = String(entry?.id || entry?.name || `p${idx + 1}`).trim();
    if (!id) return;
    participants.set(id, { id, label: String(entry?.label || entry?.name || id).trim() || id });
  });
  messagesArray.forEach((entry: any) => {
    const source = String(entry?.source || entry?.from || '').trim(), target = String(entry?.target || entry?.to || '').trim();
    if (!source || !target) return;
    if (!participants.has(source)) participants.set(source, { id: source, label: source });
    if (!participants.has(target)) participants.set(target, { id: target, label: target });
    messages.push({ source, target, text: String(entry?.text || entry?.label || '').trim(), type: String(entry?.type || 'sync').toLowerCase() });
  });
  return { participants: Array.from(participants.values()), messages };
};

const ARROW_HEAD = 7, SELF_LOOP_WIDTH = 36, SELF_LOOP_HEIGHT = 20;
const arrowHead = (x: number, y: number, forward: boolean) => {
  const dx = forward ? 1 : -1;
  return `${x},${y} ${x - ARROW_HEAD * dx},${y - ARROW_HEAD / 2} ${x - ARROW_HEAD * dx},${y + ARROW_HEAD / 2}`;
};

export const SequenceDiagram: React.FC<any> = ({ title, participants = [], messages = [], mermaid, style, height = 360 }) => {
  const model = React.useMemo(() => normalizeModel(participants, messages, mermaid), [participants, messages, mermaid]);
  const layout = React.useMemo(() => {
    const leftPad = 60, topPad = 30, headerWidth = 140, headerHeight = 36, laneGap = 180, lineTop = topPad + headerHeight + 15, msgStartY = lineTop + 30, msgStep = 48;
    const laneX = new Map<string, number>();
    model.participants.forEach((p, idx) => laneX.set(p.id, leftPad + idx * laneGap + headerWidth / 2));
    const width = Math.max(560, leftPad * 2 + (Math.max(1, model.participants.length) - 1) * laneGap + headerWidth);
    const contentHeight = Math.max(280, msgStartY + Math.max(1, model.messages.length) * msgStep + 40);
    return { leftPad, topPad, headerWidth, headerHeight, lineTop, msgStartY, msgStep, laneX, width, contentHeight };
  }, [model]);

  return (
    <section style={parseStyle(style)} className="ds-sequence-diagram">
      {title && (
        <header className="ds-sequence-diagram-header">
          <h3 className="ds-sequence-diagram-title">{getLiteral(title)}</h3>
        </header>
      )}
      <div className="ds-sequence-diagram-body">
        {!model.participants.length ? (
          <div className="ds-sequence-diagram-empty">No sequence diagram data available.</div>
        ) : (
          <div className="ds-sequence-diagram-viewport" style={{ maxHeight: Math.max(220, Number(height) || 360) }}>
            <svg width={layout.width} height={layout.contentHeight} className="ds-sequence-diagram-svg" role="img" aria-label="sequence diagram">
              {model.participants.map(p => {
                const centerX = layout.laneX.get(p.id) || 0;
                return (
                  <g key={p.id}>
                    <rect className="ds-sequence-participant-box" x={centerX - layout.headerWidth / 2} y={layout.topPad} width={layout.headerWidth} height={layout.headerHeight} rx={4} strokeWidth={1.5} />
                    <text className="ds-sequence-participant-label" x={centerX} y={layout.topPad + 22} textAnchor="middle" fontSize={11} fontWeight={700} style={{ fontFamily: 'monospace' }}>{p.label}</text>
                    <line className="ds-sequence-lifeline" x1={centerX} y1={layout.lineTop} x2={centerX} y2={layout.contentHeight - 20} strokeDasharray="4 4" strokeWidth={1} />
                  </g>
                );
              })}
              {model.messages.map((m, idx) => {
                const y = layout.msgStartY + idx * layout.msgStep, sx = layout.laneX.get(m.source), tx = layout.laneX.get(m.target);
                if (sx == null || tx == null) return null;
                const dashed = m.type === 'reply';
                if (sx === tx) {
                  return (
                    <g key={idx}>
                      <path className="ds-sequence-message-line" d={`M ${sx} ${y} L ${sx + SELF_LOOP_WIDTH} ${y} L ${sx + SELF_LOOP_WIDTH} ${y + SELF_LOOP_HEIGHT} L ${sx} ${y + SELF_LOOP_HEIGHT}`} fill="none" strokeWidth={1.5} strokeDasharray={dashed ? '4 3' : undefined} />
                      <polygon className="ds-sequence-message-arrow" points={arrowHead(sx, y + SELF_LOOP_HEIGHT, false)} />
                      {m.text && <text className="ds-sequence-message-label" x={sx + SELF_LOOP_WIDTH + 8} y={y + 14} fontSize={10} style={{ fontFamily: 'monospace' }}>{m.text}</text>}
                    </g>
                  );
                }
                return (
                  <g key={idx}>
                    <line className="ds-sequence-message-line" x1={sx} y1={y} x2={tx} y2={y} strokeWidth={1.5} strokeDasharray={dashed ? '4 3' : undefined} />
                    <polygon className="ds-sequence-message-arrow" points={arrowHead(tx, y, tx > sx)} />
                    {m.text && <text className="ds-sequence-message-label" x={Math.min(sx, tx) + Math.abs(tx - sx) / 2} y={y - 8} textAnchor="middle" fontSize={10} style={{ fontFamily: 'monospace' }}>{m.text}</text>}
                  </g>
                );
              })}
            </svg>
          </div>
        )}
      </div>
    </section>
  );
};
