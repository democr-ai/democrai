import React from 'react';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { cn } from '@/lib/utils';
import { getLiteral, toBoolean } from '@/renderers/shared';
import { parseStyle } from '@/utils/style';
import { applyTransform } from './cell_formatters';

type FieldDef = {
  field?: string;
  label?: string;
  header?: string;
  type?: string;
  format?: string;
  transform?: string;
  placeholder?: string;
};

const formatFieldValue = (
  value: any,
  fieldDef: FieldDef,
  stateModel: any,
  row: Record<string, any>,
): string => {
  if (value == null) {
    return getLiteral(fieldDef.placeholder, '-');
  }

  const colType = String(fieldDef.type || 'str').toLowerCase();
  const fmt = typeof fieldDef.format === 'string' ? fieldDef.format : '';
  if (fieldDef.transform) {
    return applyTransform(value, fieldDef.transform, { stateModel, row });
  }

  if (colType === 'bool') {
    return toBoolean(value) ? 'Yes' : 'No';
  }

  if (colType === 'int') {
    const n = Number.parseInt(String(value), 10);
    if (Number.isNaN(n)) return String(value);
    return String(n);
  }

  if (colType === 'float') {
    const n = Number.parseFloat(String(value));
    if (Number.isNaN(n)) return String(value);
    if (fmt) {
      const match = fmt.match(/^\.(\d+)f$/);
      if (match) {
        const digits = Number.parseInt(match[1], 10);
        return n.toFixed(Number.isNaN(digits) ? 2 : digits);
      }
    }
    return String(n);
  }

  if ((colType === 'date' || colType === 'datetime') && fmt) {
    const d = new Date(String(value));
    if (Number.isNaN(d.getTime())) return String(value);
    const DD = String(d.getDate()).padStart(2, '0');
    const MM = String(d.getMonth() + 1).padStart(2, '0');
    const YYYY = String(d.getFullYear());
    const HH = String(d.getHours()).padStart(2, '0');
    const mm = String(d.getMinutes()).padStart(2, '0');
    return fmt
      .replace(/%d/g, DD)
      .replace(/%m/g, MM)
      .replace(/%Y/g, YYYY)
      .replace(/%H/g, HH)
      .replace(/%M/g, mm);
  }
  return String(value);
};

const normalizeModel = (model: any, data: Record<string, any>): FieldDef[] => {
  if (Array.isArray(model) && model.length > 0) {
    return model.filter((entry) => entry && typeof entry === 'object');
  }
  return Object.keys(data || {}).map((key) => ({
    field: key,
    label: key.replace(/_/g, ' ').replace(/\b\w/g, (ch) => ch.toUpperCase()),
  }));
};

export const Descriptions: React.FC<any> = ({
  model = [],
  data = {},
  key_header = 'Property',
  value_header = 'Value',
  borders = true,
  style,
  stateModel,
}) => {
  const normalizedData = data && typeof data === 'object' ? data : {};
  const normalizedModel = normalizeModel(model, normalizedData);
  const showBorders = toBoolean(borders);

  return (
    <div
      className={cn(
        'w-full rounded-md overflow-hidden',
        showBorders ? 'border border-border' : 'border-0',
      )}
      style={parseStyle(style)}
    >
      <Table className='table-fixed w-full'>
        <TableHeader>
          <TableRow>
            <TableHead className="bg-muted/70 w-[30%] whitespace-normal break-words">{getLiteral(key_header, 'Property')}</TableHead>
            <TableHead className="bg-muted/70 whitespace-normal break-words">{getLiteral(value_header, 'Value')}</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {normalizedModel.map((fieldDef: FieldDef, idx) => {
            const key = String(fieldDef.field || '').trim();
            if (!key) return null;
            const label = getLiteral(
              fieldDef.label ?? fieldDef.header,
              key.replace(/_/g, ' ').replace(/\b\w/g, (ch) => ch.toUpperCase()),
            );
            const formattedValue = formatFieldValue(
              normalizedData[key],
              fieldDef,
              stateModel,
              normalizedData,
            );
            const isLast = idx === normalizedModel.length - 1;
            const rowClass = !showBorders || isLast ? 'border-b-0' : '';

            return (
              <TableRow key={`${key}_${idx}`} className={rowClass}>
                <TableCell className="bg-muted/40 font-medium text-muted-foreground align-top whitespace-normal break-words">{label}</TableCell>
                <TableCell className="align-top whitespace-pre-wrap break-words">{formattedValue}</TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </div>
  );
};
