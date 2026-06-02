import React from 'react';
import { parseStyle } from '@/utils/style';
import { getLiteral } from '@/renderers/shared';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
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

  const lines = text
    .split('\n')
    .map((line) => line.trim())
    .filter((line) => line && !line.startsWith('%%'));

  if (!lines.length || lines[0].toLowerCase() !== 'sequencediagram') {
    return { participants: [], messages: [] };
  }

  const participants = new Map<string, SequenceParticipant>();
  const messages: SequenceMessage[] = [];

  for (const line of lines.slice(1)) {
    const lower = line.toLowerCase();
    if (
      lower.startsWith('autonumber') ||
      lower.startsWith('note ') ||
      lower.startsWith('activate ') ||
      lower.startsWith('deactivate ') ||
      lower.startsWith('loop ') ||
      lower.startsWith('alt ') ||
      lower.startsWith('opt ') ||
      lower.startsWith('par ') ||
      lower.startsWith('and ') ||
      lower === 'else' ||
      lower === 'end'
    ) {
      continue;
    }

    const part = line.match(PARTICIPANT_RE);
    if (part) {
      const id = String(part[1] || '').trim();
      if (!id) continue;
      const label = String(part[2] || id).trim() || id;
      participants.set(id, { id, label });
      continue;
    }

    const msg = line.match(MESSAGE_RE);
    if (!msg) continue;

    const source = String(msg[1] || '').trim();
    const arrow = String(msg[2] || '').trim();
    const target = String(msg[3] || '').trim();
    const textValue = String(msg[4] || '').trim();
    if (!source || !target) continue;

    if (!participants.has(source)) participants.set(source, { id: source, label: source });
    if (!participants.has(target)) participants.set(target, { id: target, label: target });

    messages.push({
      source,
      target,
      text: textValue,
      type: arrow.startsWith('--') || arrow.startsWith('==') ? 'reply' : 'sync',
    });
  }

  return { participants: Array.from(participants.values()), messages };
};

const normalizeModel = (participantsRaw: any, messagesRaw: any, mermaid: any): SequenceModel => {
  const participantsArray = Array.isArray(participantsRaw) ? participantsRaw : [];
  const messagesArray = Array.isArray(messagesRaw) ? messagesRaw : [];

  if (!participantsArray.length && !messagesArray.length) {
    return parseMermaid(getLiteral(mermaid));
  }

  const participants = new Map<string, SequenceParticipant>();
  const messages: SequenceMessage[] = [];

  participantsArray.forEach((entry: any, idx: number) => {
    const id = String(entry?.id || entry?.name || `p${idx + 1}`).trim();
    if (!id) return;
    const label = String(entry?.label || entry?.name || id).trim() || id;
    participants.set(id, { id, label });
  });

  messagesArray.forEach((entry: any) => {
    const source = String(entry?.source || entry?.from || '').trim();
    const target = String(entry?.target || entry?.to || '').trim();
    if (!source || !target) return;

    if (!participants.has(source)) participants.set(source, { id: source, label: source });
    if (!participants.has(target)) participants.set(target, { id: target, label: target });

    messages.push({
      source,
      target,
      text: String(entry?.text || entry?.label || '').trim(),
      type: String(entry?.type || 'sync').toLowerCase(),
    });
  });

  return { participants: Array.from(participants.values()), messages };
};

const ARROW_HEAD = 7;
const SELF_LOOP_WIDTH = 36;
const SELF_LOOP_HEIGHT = 20;

const arrowHead = (x: number, y: number, forward: boolean) => {
  const dx = forward ? 1 : -1;
  const p1 = `${x - ARROW_HEAD * dx},${y - ARROW_HEAD / 2}`;
  const p2 = `${x - ARROW_HEAD * dx},${y + ARROW_HEAD / 2}`;
  return `${x},${y} ${p1} ${p2}`;
};

export const SequenceDiagram: React.FC<any> = ({ title, participants = [], messages = [], mermaid, style, height = 360 }) => {
  const model = React.useMemo(() => normalizeModel(participants, messages, mermaid), [participants, messages, mermaid]);

  const layout = React.useMemo(() => {
    const leftPad = 56;
    const topPad = 20;
    const headerWidth = 148;
    const headerHeight = 34;
    const laneGap = 180;
    const lineTop = topPad + headerHeight + 12;
    const msgStartY = lineTop + 24;
    const msgStep = 44;

    const laneX = new Map<string, number>();
    model.participants.forEach((participant, idx) => {
      laneX.set(participant.id, leftPad + idx * laneGap + headerWidth / 2);
    });

    const width = Math.max(520, leftPad * 2 + (Math.max(1, model.participants.length) - 1) * laneGap + headerWidth);
    const contentHeight = Math.max(260, msgStartY + Math.max(1, model.messages.length) * msgStep + 36);

    return {
      leftPad,
      topPad,
      headerWidth,
      headerHeight,
      lineTop,
      msgStartY,
      msgStep,
      laneX,
      width,
      contentHeight,
    };
  }, [model]);

  const minHeight = Math.max(220, Number(height) || 360);

  return (
    <Card style={parseStyle(style)}>
      {title ? (
        <CardHeader>
          <CardTitle className="text-sm">{getLiteral(title)}</CardTitle>
        </CardHeader>
      ) : null}
      <CardContent>
        {!model.participants.length ? (
          <div className="flex items-center justify-center text-sm text-muted-foreground" style={{ minHeight }}>
            No sequence diagram data
          </div>
        ) : (
          <div className="ui-data-panel ui-sequence-shell overflow-auto rounded-md border" style={{ minHeight }}>
            <svg width={layout.width} height={layout.contentHeight} role="img" aria-label="sequence diagram">
              <rect x={0} y={0} width={layout.width} height={layout.contentHeight} fill={DATA_THEME.surface.base} />

              {model.participants.map((participant) => {
                const centerX = layout.laneX.get(participant.id) || 0;
                const headerX = centerX - layout.headerWidth / 2;
                return (
                  <g key={`participant_${participant.id}`}>
                    <rect
                      x={headerX}
                      y={layout.topPad}
                      width={layout.headerWidth}
                      height={layout.headerHeight}
                      rx={7}
                      fill="var(--sequence-participant-bg)"
                      stroke="var(--sequence-participant-border)"
                    />
                    <text
                      x={centerX}
                      y={layout.topPad + 22}
                      textAnchor="middle"
                      fill={DATA_THEME.text.primary}
                      fontSize={12}
                      fontWeight={600}
                    >
                      {participant.label}
                    </text>
                    <line
                      x1={centerX}
                      y1={layout.lineTop}
                      x2={centerX}
                      y2={layout.contentHeight - 18}
                      stroke={DATA_THEME.text.subtle}
                      strokeDasharray="5 5"
                      strokeWidth={1.1}
                    />
                  </g>
                );
              })}

              {model.messages.map((message, idx) => {
                const y = layout.msgStartY + idx * layout.msgStep;
                const sx = layout.laneX.get(message.source);
                const tx = layout.laneX.get(message.target);
                if (!Number.isFinite(sx) || !Number.isFinite(tx)) return null;

                const dashed = message.type === 'reply' || message.type === 'dashed';
                const strokeColor = DATA_THEME.text.primary;

                if (sx === tx) {
                  const rightX = sx + SELF_LOOP_WIDTH;
                  const downY = y + SELF_LOOP_HEIGHT;
                  return (
                    <g key={`msg_${idx}`}>
                      <path
                        d={`M ${sx} ${y} L ${rightX} ${y} L ${rightX} ${downY} L ${sx} ${downY}`}
                        fill="none"
                        stroke={strokeColor}
                        strokeWidth={1.5}
                        strokeDasharray={dashed ? '5 4' : undefined}
                      />
                      <polygon points={arrowHead(sx, downY, false)} fill={strokeColor} />
                      {message.text ? (
                        <text x={rightX + 8} y={y - 2} fill={DATA_THEME.text.muted} fontSize={11}>
                          {message.text}
                        </text>
                      ) : null}
                    </g>
                  );
                }

                const forward = tx > sx;
                const textX = Math.min(sx, tx) + Math.abs(tx - sx) / 2;

                return (
                  <g key={`msg_${idx}`}>
                    <line
                      x1={sx}
                      y1={y}
                      x2={tx}
                      y2={y}
                      stroke={strokeColor}
                      strokeWidth={1.5}
                      strokeDasharray={dashed ? '5 4' : undefined}
                    />
                    <polygon points={arrowHead(tx, y, forward)} fill={strokeColor} />
                    {message.text ? (
                      <text x={textX} y={y - 7} textAnchor="middle" fill={DATA_THEME.text.muted} fontSize={11}>
                        {message.text}
                      </text>
                    ) : null}
                  </g>
                );
              })}
            </svg>
          </div>
        )}
      </CardContent>
    </Card>
  );
};
