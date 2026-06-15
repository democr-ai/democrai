import React from 'react';
import { parseStyle } from '@/utils/style';
import { getLiteral } from '@/renderers/shared';
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
    <article style={parseStyle(style)} className="a2ui-code-diff">
      <header className="a2ui-code-diff-header">
        <div className="a2ui-code-diff-header-main">
          <h3 className="a2ui-code-diff-title">
            {getLiteral(title || 'Code diff')}
          </h3>
          <div className="a2ui-code-diff-stats" aria-label={`${added} additions, ${removed} deletions`}>
            <span className="a2ui-code-diff-stat a2ui-code-diff-stat-add">+{added}</span>
            <span className="a2ui-code-diff-stat a2ui-code-diff-stat-remove">-{removed}</span>
          </div>
        </div>
        <div className="a2ui-code-diff-file">
          {getLiteral(filePath || 'modified file')} {oldRevision || newRevision ? `(${getLiteral(oldRevision)} → ${getLiteral(newRevision)})` : ''}
        </div>
      </header>
      <div className="a2ui-code-diff-body">
        <table className="a2ui-code-diff-table">
          <thead>
            <tr>
              {showLineNumbers && <th className="a2ui-code-diff-number-head">OLD</th>}
              {showLineNumbers && <th className="a2ui-code-diff-number-head">NEW</th>}
              <th className="a2ui-code-diff-code-head">CODE</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row, idx) => {
              const isHunk = row.kind === 'hunk';
              const isAdd = row.type === 'add';
              const isRemove = row.type === 'remove';
              
              return (
                <tr key={`diff_${idx}`} className={cn(
                  "ui-code-diff-row",
                  isHunk && "ui-code-diff-row-hunk",
                  isAdd && "ui-code-diff-row-add",
                  isRemove && "ui-code-diff-row-remove"
                )}>
                  {showLineNumbers && (
                    <td className={cn(
                      "ui-code-diff-line-number",
                      isHunk && "ui-code-diff-hunk",
                      isAdd && "ui-code-diff-add",
                      isRemove && "ui-code-diff-remove"
                    )}>
                      {row.kind === 'line' ? String(row.old || '') : ''}
                    </td>
                  )}
                  {showLineNumbers && (
                    <td className={cn(
                      "ui-code-diff-line-number",
                      isHunk && "ui-code-diff-hunk",
                      isAdd && "ui-code-diff-add",
                      isRemove && "ui-code-diff-remove"
                    )}>
                      {row.kind === 'line' ? String(row.new || '') : ''}
                    </td>
                  )}
                  <td className={cn(
                    "ui-code-diff-code-cell",
                    isHunk && "ui-code-diff-hunk",
                    isAdd && "ui-code-diff-add",
                    isRemove && "ui-code-diff-remove"
                  )}>
                    <span className="ui-code-diff-prefix">{isHunk ? '' : row.prefix}</span>
                    {row.kind === 'hunk' ? row.text : row.text}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </article>
  );
};
