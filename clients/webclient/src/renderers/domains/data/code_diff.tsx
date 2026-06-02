import React from 'react';
import { parseStyle } from '@/utils/style';
import { getLiteral } from '@/renderers/shared';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';

const rowsFromHunks = (hunks: any[]): any[] => {
  const rows: any[] = [];
  (Array.isArray(hunks) ? hunks : []).forEach((hunk: any) => {
    const oldStart = Number(hunk?.old_start ?? hunk?.oldStart ?? 0) || 0;
    const newStart = Number(hunk?.new_start ?? hunk?.newStart ?? 0) || 0;
    rows.push({ kind: 'hunk', text: getLiteral(hunk?.header || `@@ -${oldStart}, +${newStart} @@`) });
    let oldNo = oldStart;
    let newNo = newStart;
    (Array.isArray(hunk?.lines) ? hunk.lines : []).forEach((line: any) => {
      const type = String(line?.type || 'context').toLowerCase();
      const text = getLiteral(line?.text);
      const explicitOld = line?.old_no ?? line?.oldNo;
      const explicitNew = line?.new_no ?? line?.newNo;
      if (type === 'remove') {
        const oldValue = explicitOld ?? oldNo;
        rows.push({ kind: 'line', type, old: oldValue, new: '', text, prefix: '-' });
        oldNo = Number(oldValue || oldNo) + 1;
      } else if (type === 'add') {
        const newValue = explicitNew ?? newNo;
        rows.push({ kind: 'line', type, old: '', new: newValue, text, prefix: '+' });
        newNo = Number(newValue || newNo) + 1;
      } else {
        const oldValue = explicitOld ?? oldNo;
        const newValue = explicitNew ?? newNo;
        rows.push({ kind: 'line', type, old: oldValue, new: newValue, text, prefix: ' ' });
        oldNo = Number(oldValue || oldNo) + 1;
        newNo = Number(newValue || newNo) + 1;
      }
    });
  });
  return rows;
};

export const CodeDiff: React.FC<any> = ({ title, hunks = [], filePath, oldRevision, newRevision, showLineNumbers = true, style }) => {
  const rows = React.useMemo(() => rowsFromHunks(hunks), [hunks]);
  const added = rows.filter((r) => r.kind === 'line' && r.type === 'add').length;
  const removed = rows.filter((r) => r.kind === 'line' && r.type === 'remove').length;

  return (
    <Card style={parseStyle(style)}>
      {title ? <CardHeader><CardTitle className="text-sm">{getLiteral(title)}</CardTitle></CardHeader> : null}
      <CardContent className="grid gap-2">
        <div className="text-xs text-muted-foreground">{getLiteral(filePath || 'edited file')} {oldRevision || newRevision ? `${getLiteral(oldRevision)} -> ${getLiteral(newRevision)}` : ''} +{added} -{removed}</div>
        <Table>
          <TableHeader>
            <TableRow>
              {showLineNumbers ? <TableHead className="w-12">old</TableHead> : null}
              {showLineNumbers ? <TableHead className="w-12">new</TableHead> : null}
              <TableHead>text</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((row, idx) => (
              <TableRow key={`diff_${idx}`}>
                {showLineNumbers ? <TableCell>{row.kind === 'line' ? String(row.old || '') : ''}</TableCell> : null}
                {showLineNumbers ? <TableCell>{row.kind === 'line' ? String(row.new || '') : ''}</TableCell> : null}
                <TableCell className={row.kind === 'hunk' ? 'ui-code-diff-hunk' : row.type === 'add' ? 'ui-code-diff-add' : row.type === 'remove' ? 'ui-code-diff-remove' : ''}>{row.kind === 'hunk' ? row.text : `${row.prefix} ${row.text}`}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
};
