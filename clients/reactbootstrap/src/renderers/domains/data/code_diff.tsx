import React from 'react';
import { parseStyle } from '@/utils/style';
import { getLiteral } from '@/renderers/shared';
import { Card, CardBody, CardHeader, CardTitle, Table } from 'design-react-kit';
import { cn } from '@/lib/utils';

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
    <Card style={parseStyle(style)} className="a2ui-code-diff border overflow-hidden">
      <CardHeader className="bg-light border-bottom py-2">
        <div className="d-flex align-items-center justify-content-between">
          <CardTitle className="m-0 xsmall text-uppercase fw-bold text-muted">
            {getLiteral(title || 'Code diff')}
          </CardTitle>
          <div className="d-flex align-items-center gap-2 xsmall fw-bold">
            <span className="text-success">+{added}</span>
            <span className="text-danger">-{removed}</span>
          </div>
        </div>
        <div className="xsmall text-muted mt-1 font-monospace text-truncate">
          {getLiteral(filePath || 'modified file')} {oldRevision || newRevision ? `(${getLiteral(oldRevision)} → ${getLiteral(newRevision)})` : ''}
        </div>
      </CardHeader>
      <CardBody className="p-0 overflow-auto">
        <Table className="m-0 table-sm diff-table">
          <thead className="bg-light-subtle">
            <tr>
              {showLineNumbers && <th className="text-center text-muted xsmall font-monospace" style={{ width: '40px' }}>OLD</th>}
              {showLineNumbers && <th className="text-center text-muted xsmall font-monospace" style={{ width: '40px' }}>NEW</th>}
              <th className="text-muted xsmall font-monospace px-3">CODE</th>
            </tr>
          </thead>
          <tbody className="font-monospace xsmall">
            {rows.map((row, idx) => {
              const isHunk = row.kind === 'hunk';
              const isAdd = row.type === 'add';
              const isRemove = row.type === 'remove';
              
              return (
                <tr key={`diff_${idx}`} className={cn(
                  "ui-code-diff-row",
                  isHunk && "ui-code-diff-row-hunk fw-bold",
                  isAdd && "ui-code-diff-row-add",
                  isRemove && "ui-code-diff-row-remove"
                )}>
                  {showLineNumbers && (
                    <td className={cn(
                      "ui-code-diff-line-number text-center border-end py-0",
                      isHunk && "ui-code-diff-hunk",
                      isAdd && "ui-code-diff-add",
                      isRemove && "ui-code-diff-remove"
                    )}>
                      {row.kind === 'line' ? String(row.old || '') : ''}
                    </td>
                  )}
                  {showLineNumbers && (
                    <td className={cn(
                      "ui-code-diff-line-number text-center border-end py-0",
                      isHunk && "ui-code-diff-hunk",
                      isAdd && "ui-code-diff-add",
                      isRemove && "ui-code-diff-remove"
                    )}>
                      {row.kind === 'line' ? String(row.new || '') : ''}
                    </td>
                  )}
                  <td className={cn(
                    "px-3 py-0 text-nowrap ui-code-diff-code-cell",
                    isHunk && "py-1 ui-code-diff-hunk",
                    isAdd && "ui-code-diff-add",
                    isRemove && "ui-code-diff-remove"
                  )}>
                    <span className="me-2 opacity-50">{isHunk ? '' : row.prefix}</span>
                    {row.kind === 'hunk' ? row.text : row.text}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </Table>
      </CardBody>
    </Card>
  );
};
