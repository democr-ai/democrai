import React from 'react';
import { View, Text, StyleSheet, ScrollView } from 'react-native';
import Svg, { Circle, Defs, LinearGradient, Line, Path, Polygon, Rect, Stop, Text as SvgText } from 'react-native-svg';
import { getLiteral } from '../../shared';

const Box: React.FC<any> = ({ title, children, style }) => (
  <View style={[styles.box, style]}>
    {getLiteral(title) ? <Text style={styles.title}>{getLiteral(title)}</Text> : null}
    {children}
  </View>
);

const rowsFromPairs = (items: any[], getLeft: (item: any) => any, getRight: (item: any) => any) => (
  (Array.isArray(items) ? items : []).map((item, index) => (
    <View key={`pair_${index}`} style={styles.pairRow}>
      <Text style={styles.pairLeft}>{getLiteral(getLeft(item))}</Text>
      <Text style={styles.pairArrow}>{'->'}</Text>
      <Text style={styles.pairRight}>{getLiteral(getRight(item))}</Text>
    </View>
  ))
);

const pointsForValues = (values: number[], width: number, height: number): Array<{ x: number; y: number; value: number }> => {
  const maxVal = Math.max(...values, 1);
  const minVal = Math.min(...values, 0);
  const range = Math.max(1, maxVal - minVal);
  return values.map((value, index) => ({
    x: values.length === 1 ? width / 2 : (index / (values.length - 1)) * width,
    y: height - ((value - minVal) / range) * height,
    value,
  }));
};

const ChartLineArea: React.FC<{ values: number[]; labels: any[]; mode: 'line' | 'area' }> = ({ values, labels, mode }) => {
  const width = Math.max(260, values.length * 54);
  const height = 140;
  const points = pointsForValues(values, width - 24, height - 20).map((point) => ({ ...point, x: point.x + 12, y: point.y + 10 }));
  const linePath = points.map((point, index) => `${index === 0 ? 'M' : 'L'} ${point.x} ${point.y}`).join(' ');
  const areaPath = `${linePath} L ${points[points.length - 1].x} ${height} L ${points[0].x} ${height} Z`;

  return (
    <ScrollView horizontal showsHorizontalScrollIndicator={false}>
      <View>
        <Svg width={width} height={height}>
          <Defs>
            <LinearGradient id="chartArea" x1="0" y1="0" x2="0" y2="1">
              <Stop offset="0" stopColor="#58A6FF" stopOpacity="0.42" />
              <Stop offset="1" stopColor="#58A6FF" stopOpacity="0.04" />
            </LinearGradient>
          </Defs>
          {[0, 1, 2, 3].map((entry) => {
            const y = 10 + entry * ((height - 20) / 3);
            return <Line key={`grid_${entry}`} x1={0} y1={y} x2={width} y2={y} stroke="#30363D" strokeWidth={1} />;
          })}
          {mode === 'area' ? <Path d={areaPath} fill="url(#chartArea)" /> : null}
          <Path d={linePath} fill="none" stroke="#58A6FF" strokeWidth={3} strokeLinecap="round" strokeLinejoin="round" />
          {points.map((point, index) => (
            <Circle key={`dot_${index}`} cx={point.x} cy={point.y} r={4} fill="#0D1117" stroke="#58A6FF" strokeWidth={2} />
          ))}
        </Svg>
        <View style={[styles.chartLabels, { width }]}>
          {values.map((value, index) => (
            <View key={`line_label_${index}`} style={styles.lineLabelSlot}>
              <Text style={styles.barValue}>{value}</Text>
              {labels[index] != null ? <Text style={styles.barLabel} numberOfLines={1}>{getLiteral(labels[index])}</Text> : null}
            </View>
          ))}
        </View>
      </View>
    </ScrollView>
  );
};

export const Chart: React.FC<any> = ({ chartType = 'bar', type, data = [], labels = [], title, style }) => {
  const values = Array.isArray(data) ? data.map(Number).filter(Number.isFinite) : [];
  const resolvedType = String(type || chartType || 'bar').trim().toLowerCase();
  const maxVal = Math.max(...values, 1);
  if (!values.length) {
    return <Text style={[styles.empty, style]}>No data available</Text>;
  }
  if (resolvedType === 'line' || resolvedType === 'area') {
    return (
      <Box title={title || resolvedType} style={style}>
        <ChartLineArea values={values} labels={labels} mode={resolvedType} />
      </Box>
    );
  }
  return (
    <Box title={title || resolvedType} style={style}>
      <View style={styles.chart}>
        {values.map((value, index) => {
          const height = Math.max(4, Math.round((value / maxVal) * 120));
          return (
            <View key={`bar_${index}`} style={styles.barSlot}>
              <View style={[styles.bar, { height }]} />
              <Text style={styles.barValue}>{value}</Text>
              {labels[index] != null ? <Text style={styles.barLabel} numberOfLines={1}>{getLiteral(labels[index])}</Text> : null}
            </View>
          );
        })}
      </View>
    </Box>
  );
};

export const Diagram: React.FC<any> = ({ title, nodes = [], edges = [], mermaid, style }) => {
  const parsedEdges = Array.isArray(edges) && edges.length
    ? edges
    : getLiteral(mermaid).split('\n').filter((line) => line.includes('-->')).map((line) => {
      const [source, target] = line.split('-->');
      return { source: source?.trim(), target: target?.trim() };
    });
  return (
    <Box title={title || 'Diagram'} style={style}>
      {Array.isArray(nodes) && nodes.length ? (
        <View style={styles.chipWrap}>
          {nodes.map((node: any, index: number) => (
            <Text key={`node_${index}`} style={styles.nodeChip}>{getLiteral(node?.label || node?.id || node)}</Text>
          ))}
        </View>
      ) : null}
      {rowsFromPairs(parsedEdges, (edge) => edge?.source || edge?.from, (edge) => edge?.target || edge?.to)}
      {!parsedEdges.length && !nodes?.length ? <Text style={styles.empty}>No nodes</Text> : null}
    </Box>
  );
};

const diffRowsFromHunks = (hunks: any[]): Array<{ type: string; text: string; prefix: string }> => {
  const rows: Array<{ type: string; text: string; prefix: string }> = [];
  (Array.isArray(hunks) ? hunks : []).forEach((hunk) => {
    rows.push({ type: 'hunk', text: getLiteral(hunk?.header || '@@'), prefix: '' });
    (Array.isArray(hunk?.lines) ? hunk.lines : []).forEach((line: any) => {
      const type = String(line?.type || 'context').toLowerCase();
      rows.push({
        type,
        text: getLiteral(line?.text),
        prefix: type === 'add' ? '+' : type === 'remove' ? '-' : ' ',
      });
    });
  });
  return rows;
};

export const CodeDiff: React.FC<any> = ({ title, hunks = [], filePath, style }) => {
  const rows = React.useMemo(() => diffRowsFromHunks(hunks), [hunks]);
  return (
    <Box title={title || filePath || 'Diff'} style={style}>
      <ScrollView horizontal>
        <View style={styles.codeBlock}>
          {rows.length ? rows.map((row, index) => (
            <Text
              key={`diff_${index}`}
              style={[
                styles.codeLine,
                row.type === 'add' && styles.codeAdd,
                row.type === 'remove' && styles.codeRemove,
                row.type === 'hunk' && styles.codeHunk,
              ]}
            >
              {row.type === 'hunk' ? row.text : `${row.prefix} ${row.text}`}
            </Text>
          )) : <Text style={styles.empty}>No differences</Text>}
        </View>
      </ScrollView>
    </Box>
  );
};

type SequenceParticipant = { id: string; label: string };
type SequenceMessage = { source: string; target: string; text: string; type: string };

const PARTICIPANT_RE = /^(?:participant|actor)\s+([A-Za-z0-9_.-]+)(?:\s+as\s+(.+))?$/i;
const MESSAGE_RE = /^([A-Za-z0-9_.-]+)\s*(-->>|->>|-->|->|--x|-x|==>>|=>>|==>|=>)\s*([A-Za-z0-9_.-]+)\s*:\s*(.+)$/;

const parseSequenceMermaid = (raw: string): { participants: SequenceParticipant[]; messages: SequenceMessage[] } => {
  const lines = String(raw || '').split('\n').map((line) => line.trim()).filter((line) => line && !line.startsWith('%%'));
  if (!lines.length || lines[0].toLowerCase() !== 'sequencediagram') return { participants: [], messages: [] };
  const participantMap = new Map<string, SequenceParticipant>();
  const parsed: SequenceMessage[] = [];

  lines.slice(1).forEach((line) => {
    const participant = line.match(PARTICIPANT_RE);
    if (participant) {
      const id = String(participant[1] || '').trim();
      if (id) participantMap.set(id, { id, label: String(participant[2] || id).trim() || id });
      return;
    }
    const msg = line.match(MESSAGE_RE);
    if (!msg) return;
    const source = String(msg[1] || '').trim();
    const arrow = String(msg[2] || '').trim();
    const target = String(msg[3] || '').trim();
    if (!source || !target) return;
    if (!participantMap.has(source)) participantMap.set(source, { id: source, label: source });
    if (!participantMap.has(target)) participantMap.set(target, { id: target, label: target });
    parsed.push({
      source,
      target,
      text: String(msg[4] || '').trim(),
      type: arrow.startsWith('--') || arrow.startsWith('==') ? 'reply' : 'sync',
    });
  });

  return { participants: Array.from(participantMap.values()), messages: parsed };
};

const normalizeSequence = (participantsRaw: any[], messagesRaw: any[], mermaid: any) => {
  if ((!Array.isArray(participantsRaw) || !participantsRaw.length) && (!Array.isArray(messagesRaw) || !messagesRaw.length)) {
    return parseSequenceMermaid(getLiteral(mermaid));
  }
  const participantMap = new Map<string, SequenceParticipant>();
  const parsed: SequenceMessage[] = [];
  (Array.isArray(participantsRaw) ? participantsRaw : []).forEach((entry, index) => {
    const id = String(entry?.id || entry?.name || `p${index + 1}`).trim();
    if (id) participantMap.set(id, { id, label: getLiteral(entry?.label || entry?.name || id) });
  });
  (Array.isArray(messagesRaw) ? messagesRaw : []).forEach((entry) => {
    const source = String(entry?.source || entry?.from || '').trim();
    const target = String(entry?.target || entry?.to || '').trim();
    if (!source || !target) return;
    if (!participantMap.has(source)) participantMap.set(source, { id: source, label: source });
    if (!participantMap.has(target)) participantMap.set(target, { id: target, label: target });
    parsed.push({
      source,
      target,
      text: getLiteral(entry?.text || entry?.label || ''),
      type: String(entry?.type || 'sync').toLowerCase(),
    });
  });
  return { participants: Array.from(participantMap.values()), messages: parsed };
};

const arrowHeadPoints = (x: number, y: number, forward: boolean): string => {
  const dx = forward ? 1 : -1;
  return `${x},${y} ${x - 8 * dx},${y - 5} ${x - 8 * dx},${y + 5}`;
};

export const SequenceDiagram: React.FC<any> = ({ title, participants = [], messages = [], mermaid, style, height = 320 }) => {
  const model = React.useMemo(() => normalizeSequence(participants, messages, mermaid), [participants, messages, mermaid]);
  const laneGap = 168;
  const headerWidth = 126;
  const top = 16;
  const headerHeight = 34;
  const lineTop = top + headerHeight + 12;
  const msgStartY = lineTop + 28;
  const msgStep = 46;
  const width = Math.max(330, 44 + Math.max(1, model.participants.length - 1) * laneGap + headerWidth + 44);
  const contentHeight = Math.max(Number(height) || 320, msgStartY + Math.max(1, model.messages.length) * msgStep + 36);
  const laneX = new Map<string, number>();
  model.participants.forEach((participant, index) => laneX.set(participant.id, 44 + index * laneGap + headerWidth / 2));

  return (
    <Box title={title || 'Sequence'} style={style}>
      {!model.participants.length ? <Text style={styles.empty}>No sequence diagram data</Text> : (
        <ScrollView horizontal showsHorizontalScrollIndicator={false}>
          <Svg width={width} height={contentHeight}>
            <Rect x={0} y={0} width={width} height={contentHeight} fill="#0D1117" />
            {model.participants.map((participant) => {
              const cx = laneX.get(participant.id) || 0;
              const x = cx - headerWidth / 2;
              return (
                <React.Fragment key={`participant_${participant.id}`}>
                  <Rect x={x} y={top} width={headerWidth} height={headerHeight} rx={7} fill="#161B22" stroke="#30363D" />
                  <SvgText x={cx} y={top + 22} fill="#E6EDF3" fontSize={12} fontWeight="600" textAnchor="middle">
                    {participant.label}
                  </SvgText>
                  <Line x1={cx} y1={lineTop} x2={cx} y2={contentHeight - 18} stroke="#484F58" strokeWidth={1} strokeDasharray="5 5" />
                </React.Fragment>
              );
            })}
            {model.messages.map((message, index) => {
              const y = msgStartY + index * msgStep;
              const sx = laneX.get(message.source);
              const tx = laneX.get(message.target);
              if (sx == null || tx == null) return null;
              const dashed = message.type === 'reply' || message.type === 'dashed';
              if (sx === tx) {
                const right = sx + 36;
                const down = y + 20;
                return (
                  <React.Fragment key={`message_${index}`}>
                    <Path d={`M ${sx} ${y} L ${right} ${y} L ${right} ${down} L ${sx} ${down}`} fill="none" stroke="#C9D1D9" strokeWidth={1.5} strokeDasharray={dashed ? '5 4' : undefined} />
                    <Polygon points={arrowHeadPoints(sx, down, false)} fill="#C9D1D9" />
                    <SvgText x={right + 8} y={y - 4} fill="#8B949E" fontSize={11}>{message.text}</SvgText>
                  </React.Fragment>
                );
              }
              const forward = tx > sx;
              const textX = Math.min(sx, tx) + Math.abs(tx - sx) / 2;
              return (
                <React.Fragment key={`message_${index}`}>
                  <Line x1={sx} y1={y} x2={tx} y2={y} stroke="#C9D1D9" strokeWidth={1.5} strokeDasharray={dashed ? '5 4' : undefined} />
                  <Polygon points={arrowHeadPoints(tx, y, forward)} fill="#C9D1D9" />
                  {message.text ? (
                    <SvgText x={textX} y={y - 7} fill="#8B949E" fontSize={11} textAnchor="middle">
                      {message.text.length > 28 ? `${message.text.slice(0, 25)}...` : message.text}
                    </SvgText>
                  ) : null}
                </React.Fragment>
              );
            })}
          </Svg>
        </ScrollView>
      )}
    </Box>
  );
};

const DAY_MS = 24 * 60 * 60 * 1000;
const GANTT_COLORS: Record<string, string> = {
  done: '#3FB950',
  active: '#58A6FF',
  planned: '#8B949E',
  risk: '#D29922',
  blocked: '#F85149',
};

const parseGanttDate = (raw: any): Date | null => {
  const value = String(raw || '').trim();
  if (!value) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  date.setHours(0, 0, 0, 0);
  return date;
};

const daysBetween = (start: Date, end: Date): number => Math.max(0, Math.round((end.getTime() - start.getTime()) / DAY_MS));

const addDays = (date: Date, days: number): Date => {
  const next = new Date(date.getTime() + days * DAY_MS);
  next.setHours(0, 0, 0, 0);
  return next;
};

const flattenGanttItems = (rawItems: any[], depth = 0): any[] => (
  (Array.isArray(rawItems) ? rawItems : []).flatMap((item, index) => {
    if (!item || typeof item !== 'object') return [];
    const children = Array.isArray(item.subtasks) ? item.subtasks : (Array.isArray(item.children) ? item.children : []);
    const current = {
      id: String(item.id || `task_${depth}_${index}`),
      label: getLiteral(item.label || item.name || item.title || `Task ${index + 1}`),
      start: parseGanttDate(item.start),
      end: parseGanttDate(item.end) || parseGanttDate(item.start),
      status: String(item.status || 'planned').toLowerCase(),
      progress: Math.max(0, Math.min(100, Number(item.progress || 0))),
      group: getLiteral(item.group || ''),
      depth,
      color: /^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$/.test(String(item.color || '')) ? item.color : undefined,
    };
    return [current, ...flattenGanttItems(children, depth + 1)];
  })
);

export const Gantt: React.FC<any> = ({ title, items = [], start, end, scale = '1d', height = 360, style }) => {
  const rows = React.useMemo(() => flattenGanttItems(items).filter((row) => row.start && row.end), [items]);
  if (!rows.length) {
    return <Box title={title || 'Gantt'} style={style}><Text style={styles.empty}>No gantt data</Text></Box>;
  }

  const minStart = parseGanttDate(start) || new Date(Math.min(...rows.map((row) => row.start.getTime())));
  const maxEnd = parseGanttDate(end) || new Date(Math.max(...rows.map((row) => row.end.getTime())));
  const dayWidth = String(scale).includes('h') ? 56 : 28;
  const totalDays = Math.max(1, daysBetween(minStart, maxEnd) + 1);
  const timelineWidth = totalDays * dayWidth;
  const rowHeight = 42;
  const chartHeight = Math.min(Math.max(220, Number(height) || 360), 520);
  const ticks = Array.from({ length: totalDays }, (_entry, index) => addDays(minStart, index));

  return (
    <Box title={title || 'Gantt'} style={style}>
      <View style={[styles.ganttShell, { maxHeight: chartHeight }]}>
        <View style={styles.ganttLabels}>
          <View style={styles.ganttHeaderCell}><Text style={styles.ganttHeaderText}>Task</Text></View>
          {rows.map((row) => (
            <View key={`label_${row.id}`} style={[styles.ganttLabelRow, { height: rowHeight, paddingLeft: 8 + row.depth * 12 }]}>
              <Text style={styles.ganttTaskLabel} numberOfLines={1}>{row.label}</Text>
              {row.group ? <Text style={styles.ganttTaskGroup} numberOfLines={1}>{row.group}</Text> : null}
            </View>
          ))}
        </View>
        <ScrollView horizontal showsHorizontalScrollIndicator>
          <View style={{ width: timelineWidth }}>
            <View style={styles.ganttTimelineHeader}>
              {ticks.map((date) => (
                <View key={`tick_${date.toISOString()}`} style={[styles.ganttTick, { width: dayWidth }]}>
                  <Text style={styles.ganttTickText}>{date.getDate()}</Text>
                </View>
              ))}
            </View>
            {rows.map((row) => {
              const left = daysBetween(minStart, row.start) * dayWidth;
              const width = Math.max(10, (daysBetween(row.start, row.end) + 1) * dayWidth);
              const color = row.color || GANTT_COLORS[row.status] || GANTT_COLORS.planned;
              return (
                <View key={`bar_${row.id}`} style={[styles.ganttTimelineRow, { height: rowHeight }]}>
                  {ticks.map((date) => (
                    <View key={`grid_${row.id}_${date.toISOString()}`} style={[styles.ganttGridCell, { width: dayWidth }]} />
                  ))}
                  <View style={[styles.ganttBar, { left, width, backgroundColor: color }]}>
                    {row.progress > 0 ? <View style={[styles.ganttProgress, { width: `${row.progress}%` }]} /> : null}
                  </View>
                </View>
              );
            })}
          </View>
        </ScrollView>
      </View>
    </Box>
  );
};

const GIT_PALETTE = ['#58A6FF', '#3FB950', '#D29922', '#F778BA', '#A371F7', '#FF7B72'];

const normalizeGitCommits = (rawCommits: any[]) => {
  const branchToLane = new Map<string, number>();
  return (Array.isArray(rawCommits) ? rawCommits : []).map((raw, index) => {
    const id = String(raw?.id || raw?.hash || `c${index + 1}`).trim();
    const branch = String(raw?.branch || raw?.laneName || '').trim();
    const laneRaw = Number(raw?.lane);
    let lane = Number.isFinite(laneRaw) ? Math.max(0, Math.trunc(laneRaw)) : -1;
    if (lane < 0) {
      const key = branch.toLowerCase() || 'main';
      if (!branchToLane.has(key)) branchToLane.set(key, branchToLane.size);
      lane = branchToLane.get(key) || 0;
    }
    return {
      id,
      label: getLiteral(raw?.label || raw?.message || id),
      branch,
      lane,
      color: /^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$/.test(String(raw?.color || '')) ? raw.color : GIT_PALETTE[lane % GIT_PALETTE.length],
    };
  }).filter((entry) => entry.id);
};

const normalizeGitEdges = (rawEdges: any[], commits: any[]) => {
  const ids = new Set(commits.map((entry) => entry.id));
  const explicit = (Array.isArray(rawEdges) ? rawEdges : [])
    .map((raw) => ({ source: String(raw?.source || raw?.from || '').trim(), target: String(raw?.target || raw?.to || '').trim() }))
    .filter((entry) => entry.source && entry.target && ids.has(entry.source) && ids.has(entry.target));
  if (explicit.length) return explicit;
  return commits.slice(0, -1).map((entry, index) => ({ source: entry.id, target: commits[index + 1].id }));
};

export const GitGraph: React.FC<any> = ({ title, commits = [], items = [], edges = [], laneWidth = 86, rowHeight = 58, showLabels = true, height = 360, style }) => {
  const normalized = React.useMemo(() => normalizeGitCommits(Array.isArray(commits) && commits.length ? commits : items), [commits, items]);
  const graphEdges = React.useMemo(() => normalizeGitEdges(edges, normalized), [edges, normalized]);
  const laneStep = Math.max(64, Number(laneWidth) || 86);
  const rowStep = Math.max(46, Number(rowHeight) || 58);
  const leftPad = 38;
  const topPad = 30;
  const maxLane = Math.max(0, ...normalized.map((entry) => entry.lane));
  const width = Math.max(330, leftPad * 2 + maxLane * laneStep + 260);
  const svgHeight = Math.max(Number(height) || 360, topPad * 2 + Math.max(1, normalized.length) * rowStep);
  const pos = new Map(normalized.map((entry, index) => [entry.id, {
    x: leftPad + entry.lane * laneStep,
    y: topPad + index * rowStep,
    commit: entry,
  }]));

  return (
    <Box title={title || 'Git'} style={style}>
      {!normalized.length ? <Text style={styles.empty}>No git graph data</Text> : (
        <ScrollView horizontal showsHorizontalScrollIndicator={false}>
          <ScrollView style={{ maxHeight: Number(height) || 360 }} nestedScrollEnabled>
            <Svg width={width} height={svgHeight}>
              <Rect x={0} y={0} width={width} height={svgHeight} fill="#0D1117" />
              {Array.from({ length: maxLane + 1 }).map((_entry, lane) => {
                const x = leftPad + lane * laneStep;
                return <Line key={`lane_${lane}`} x1={x} y1={18} x2={x} y2={svgHeight - 18} stroke="#30363D" strokeWidth={1} strokeDasharray="4 6" />;
              })}
              {graphEdges.map((edge, index) => {
                const source = pos.get(edge.source);
                const target = pos.get(edge.target);
                if (!source || !target) return null;
                const midY = (source.y + target.y) / 2;
                const d = source.x === target.x
                  ? `M ${source.x} ${source.y} L ${target.x} ${target.y}`
                  : `M ${source.x} ${source.y} C ${source.x} ${midY}, ${target.x} ${midY}, ${target.x} ${target.y}`;
                return <Path key={`edge_${index}`} d={d} fill="none" stroke={target.commit.color} strokeWidth={2.2} strokeLinecap="round" />;
              })}
              {normalized.map((commit, index) => {
                const point = pos.get(commit.id)!;
                return (
                  <React.Fragment key={`commit_${commit.id}_${index}`}>
                    <Circle cx={point.x} cy={point.y} r={7} fill={commit.color} stroke="#0D1117" strokeWidth={2} />
                    {showLabels ? (
                      <>
                        <SvgText x={point.x + 16} y={point.y - 2} fill="#E6EDF3" fontSize={12} fontWeight="600">
                          {commit.label.length > 34 ? `${commit.label.slice(0, 31)}...` : commit.label}
                        </SvgText>
                        {commit.branch ? <SvgText x={point.x + 16} y={point.y + 14} fill="#8B949E" fontSize={10}>{commit.branch}</SvgText> : null}
                      </>
                    ) : null}
                  </React.Fragment>
                );
              })}
            </Svg>
          </ScrollView>
        </ScrollView>
      )}
    </Box>
  );
};

export const Workflow: React.FC<any> = ({ title, nodes = [], steps = [], edges = [], style }) => {
  const rows = Array.isArray(steps) && steps.length ? steps : nodes;
  return (
    <Box title={title || 'Workflow'} style={style}>
      {(Array.isArray(rows) ? rows : []).map((step: any, index: number) => (
        <View key={`step_${index}`} style={styles.stepRow}>
          <Text style={styles.stepIndex}>{index + 1}</Text>
          <Text style={styles.taskTitle}>{getLiteral(step?.label || step?.title || step?.id || step)}</Text>
        </View>
      ))}
      {Array.isArray(edges) && edges.length ? rowsFromPairs(edges, (edge) => edge?.source || edge?.from, (edge) => edge?.target || edge?.to) : null}
    </Box>
  );
};

export const DashboardWidget: React.FC<any> = ({ title, ExplicitList, style }) => (
  <Box title={title} style={style}>{ExplicitList}</Box>
);

export const GridDropZone: React.FC<any> = ({ title, ExplicitList, style }) => (
  <Box title={title || 'Drop zone'} style={[styles.dropZone, style]}>{ExplicitList}</Box>
);

const styles = StyleSheet.create({
  box: {
    width: '100%',
    borderWidth: 1,
    borderColor: '#30363D',
    borderRadius: 8,
    backgroundColor: '#161B22',
    padding: 12,
    marginVertical: 6,
  },
  title: { color: '#E6EDF3', fontSize: 14, fontWeight: '700', marginBottom: 10 },
  empty: { color: '#6E7681', fontSize: 13, paddingVertical: 8 },
  chart: { minHeight: 150, flexDirection: 'row', alignItems: 'flex-end', gap: 8 },
  barSlot: { flex: 1, minWidth: 28, alignItems: 'center', justifyContent: 'flex-end' },
  bar: { width: '70%', borderRadius: 4, backgroundColor: '#58A6FF' },
  barValue: { color: '#C9D1D9', fontSize: 10, marginTop: 4 },
  barLabel: { color: '#6E7681', fontSize: 10, marginTop: 2, maxWidth: 60 },
  chartLabels: { flexDirection: 'row', paddingHorizontal: 4, marginTop: 2 },
  lineLabelSlot: { flex: 1, minWidth: 44, alignItems: 'center' },
  chipWrap: { flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginBottom: 8 },
  nodeChip: { color: '#C9D1D9', fontSize: 12, borderWidth: 1, borderColor: '#30363D', borderRadius: 6, paddingHorizontal: 8, paddingVertical: 5 },
  pairRow: { flexDirection: 'row', alignItems: 'center', gap: 8, paddingVertical: 5 },
  pairLeft: { color: '#E6EDF3', fontSize: 13, fontWeight: '600' },
  pairArrow: { color: '#6E7681', fontSize: 12 },
  pairRight: { color: '#C9D1D9', fontSize: 13, flex: 1 },
  codeBlock: { minWidth: 320, borderRadius: 6, overflow: 'hidden', backgroundColor: '#0D1117' },
  codeLine: { color: '#C9D1D9', fontFamily: 'Menlo', fontSize: 12, paddingHorizontal: 8, paddingVertical: 3 },
  codeAdd: { backgroundColor: '#12361F', color: '#AFF5B4' },
  codeRemove: { backgroundColor: '#3B1218', color: '#FFDCD7' },
  codeHunk: { backgroundColor: '#1F6FEB26', color: '#79C0FF' },
  ganttShell: {
    flexDirection: 'row',
    borderWidth: 1,
    borderColor: '#30363D',
    borderRadius: 8,
    overflow: 'hidden',
    backgroundColor: '#0D1117',
  },
  ganttLabels: {
    width: 132,
    borderRightWidth: 1,
    borderRightColor: '#30363D',
    backgroundColor: '#161B22',
  },
  ganttHeaderCell: {
    height: 34,
    justifyContent: 'center',
    paddingHorizontal: 10,
    borderBottomWidth: 1,
    borderBottomColor: '#30363D',
    backgroundColor: '#21262D',
  },
  ganttHeaderText: {
    color: '#E6EDF3',
    fontSize: 11,
    fontWeight: '700',
    textTransform: 'uppercase',
  },
  ganttLabelRow: {
    justifyContent: 'center',
    borderBottomWidth: 1,
    borderBottomColor: '#21262D',
    paddingRight: 8,
  },
  ganttTaskLabel: {
    color: '#E6EDF3',
    fontSize: 12,
    fontWeight: '600',
  },
  ganttTaskGroup: {
    color: '#8B949E',
    fontSize: 10,
    marginTop: 2,
  },
  ganttTimelineHeader: {
    height: 34,
    flexDirection: 'row',
    borderBottomWidth: 1,
    borderBottomColor: '#30363D',
    backgroundColor: '#161B22',
  },
  ganttTick: {
    justifyContent: 'center',
    alignItems: 'center',
    borderRightWidth: 1,
    borderRightColor: '#30363D',
  },
  ganttTickText: {
    color: '#8B949E',
    fontSize: 10,
    fontWeight: '600',
  },
  ganttTimelineRow: {
    position: 'relative',
    flexDirection: 'row',
    borderBottomWidth: 1,
    borderBottomColor: '#21262D',
  },
  ganttGridCell: {
    height: '100%',
    borderRightWidth: 1,
    borderRightColor: '#21262D',
  },
  ganttBar: {
    position: 'absolute',
    top: 11,
    height: 20,
    borderRadius: 5,
    overflow: 'hidden',
    borderWidth: 1,
    borderColor: '#FFFFFF24',
  },
  ganttProgress: {
    height: '100%',
    backgroundColor: '#FFFFFF42',
  },
  taskRow: { borderTopWidth: 1, borderTopColor: '#30363D', paddingVertical: 8 },
  taskTitle: { color: '#E6EDF3', fontSize: 13, fontWeight: '600' },
  taskMeta: { color: '#8B949E', fontSize: 12, marginTop: 2 },
  commitRow: { flexDirection: 'row', gap: 10, alignItems: 'flex-start', paddingVertical: 7 },
  commitDot: { width: 10, height: 10, borderRadius: 5, backgroundColor: '#58A6FF', marginTop: 4 },
  stepRow: { flexDirection: 'row', gap: 8, alignItems: 'center', paddingVertical: 6 },
  stepIndex: { width: 22, height: 22, borderRadius: 11, backgroundColor: '#238636', color: '#FFFFFF', textAlign: 'center', lineHeight: 22, fontSize: 12, fontWeight: '700' },
  dropZone: { borderStyle: 'dashed' },
});
