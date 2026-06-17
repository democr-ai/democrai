import React from 'react';
import { Button } from 'design-react-kit';
import { TextField } from './text_field';
import { TextArea } from './textarea';
import { Checkbox } from './checkbox';
import { RadioGroup } from './radio_group';
import { Select } from './select';
import { Attachment } from './attachment';
import { AudioRecorder } from './audio_recorder';
import { DatePicker } from './date_picker';
import { Toggle } from './toggle';
import { TagsInput } from './tags_input';
import { EditableList } from './editable_list';
import { emitActionSpec, isAnyTrackedActionPending } from '@/renderers/shared';
import { evaluateRule } from '@/renderers/rules';
import {
  inferModuleNameFromAction,
  materializeAttachmentUploads,
} from '@/utils/uploads';

const getLiteral = (value: any): string => {
  if (typeof value === 'string') return value;
  if (value && typeof value === 'object' && typeof value.literalString === 'string') return value.literalString;
  return value == null ? '' : String(value);
};

const arraysEqual = (left: any[], right: any[]): boolean => {
  if (left.length !== right.length) return false;
  for (let i = 0; i < left.length; i += 1) {
    if (left[i] !== right[i]) return false;
  }
  return true;
};

const valuesEqual = (left: any, right: any): boolean => {
  if (Array.isArray(left) && Array.isArray(right)) return arraysEqual(left, right);
  return left === right;
};

const isLayoutNode = (node: any): boolean => {
  const t = String(node?.type || '').toLowerCase();
  return t === 'row' || t === 'column';
};

const getNodeChildren = (node: any): any[] => {
  const children = node?.children ?? node?.items ?? [];
  return Array.isArray(children) ? children.filter((child) => child && typeof child === 'object') : [];
};

const mergeInitialValues = (nodes: any, values: Record<string, any> | null): any[] => {
  const modelNodes = Array.isArray(nodes) ? nodes.filter((node) => node && typeof node === 'object') : [];
  if (!values || Object.keys(values).length === 0) return modelNodes.map((node) => ({ ...node }));

  const apply = (node: any): any => {
    if (!node || typeof node !== 'object') return node;
    const next = { ...node };

    if (isLayoutNode(next)) {
      if (Array.isArray(next.children)) {
        next.children = next.children.map((child: any) => apply(child));
      } else if (Array.isArray(next.items)) {
        next.items = next.items.map((child: any) => apply(child));
      }
      return next;
    }

    const name = String(next?.name || '').trim();
    if (name && Object.prototype.hasOwnProperty.call(values, name)) {
      next.value = values[name];
    }
    return next;
  };

  return modelNodes.map((node) => apply(node));
};

const resolveFieldKey = (field: any, fallback: string): string => {
  const name = field?.name;
  if (typeof name === 'string' && name.trim()) return name.trim();
  const id = field?.id;
  if (typeof id === 'string' && id.trim()) return id.trim();
  return fallback;
};

type FieldEntry = {
  key: string;
  field: any;
};

const collectFieldEntries = (nodes: any[], path = 'root'): FieldEntry[] => {
  const entries: FieldEntry[] = [];
  nodes.forEach((node: any, index: number) => {
    if (!node || typeof node !== 'object') return;
    const nodePath = `${path}_${index}`;
    if (isLayoutNode(node)) {
      entries.push(...collectFieldEntries(getNodeChildren(node), nodePath));
      return;
    }
    entries.push({
      key: resolveFieldKey(node, `field_${nodePath}`),
      field: node,
    });
  });
  return entries;
};

const normalizeInitialValue = (field: any): any => {
  const type = String(field?.type || 'text').toLowerCase();
  const raw = field?.value;

  if (type === 'checkbox' || type === 'toggle' || type === 'switch') return Boolean(raw);
  if (type === 'select' && field?.multiple) return Array.isArray(raw) ? raw : [];
  if (type === 'tags' || type === 'tags_input') return Array.isArray(raw) ? raw : [];
  if (type === 'editable_list') return Array.isArray(raw) ? raw : [];
  if (type === 'file' || type === 'attachment' || type === 'audio_recorder') return Array.isArray(raw) ? raw : [];
  if (raw == null) return '';

  if (typeof raw === 'object' && raw !== null && typeof raw.literalString === 'string') {
    return raw.literalString;
  }

  return raw;
};

const normalizeFieldValue = (field: any, value: any): any => {
  const type = String(field?.type || 'text').toLowerCase();
  if (type === 'checkbox' || type === 'toggle' || type === 'switch') return Boolean(value);
  if (type === 'select' && field?.multiple) return Array.isArray(value) ? value : [];
  if (type === 'tags' || type === 'tags_input') return Array.isArray(value) ? value : [];
  if (type === 'editable_list') return Array.isArray(value) ? value : [];
  if (type === 'file' || type === 'attachment' || type === 'audio_recorder') return Array.isArray(value) ? value : [];
  return value ?? '';
};

const getActionName = (action: any): string => {
  if (typeof action === 'string') return action;
  if (action && typeof action === 'object' && typeof action.name === 'string') return action.name;
  return '';
};

const buildInitialValues = (entries: FieldEntry[]): Record<string, any> => {
  const initial: Record<string, any> = {};
  entries.forEach(({ key, field }) => {
    initial[key] = normalizeInitialValue(field);
  });
  return initial;
};

const buildModelSignature = (entries: FieldEntry[]): string => entries
  .map(({ key, field }) => {
    const type = String(field?.type || 'text');
    const initial = normalizeInitialValue(field);
    return `${key}:${type}:${JSON.stringify(initial)}`;
  })
  .join('|');

const validateAllFields = (
  entries: FieldEntry[],
  values: Record<string, any>,
): Record<string, string> => {
  const nextErrors: Record<string, string> = {};
  entries.forEach(({ key, field }) => {
    const err = validateField(field, values[key], values);
    if (err) nextErrors[key] = err;
  });
  return nextErrors;
};

const isFieldVisible = (field: any, values: Record<string, any>): boolean => {
  if (field?.show_if !== undefined && !evaluateRule(field.show_if, { formValues: values }, true)) {
    return false;
  }
  if (field?.hide_if !== undefined && evaluateRule(field.hide_if, { formValues: values }, false)) {
    return false;
  }
  return true;
};

const pickVisibleValues = (
  entries: FieldEntry[],
  values: Record<string, any>,
): Record<string, any> => {
  const next: Record<string, any> = {};
  entries.forEach(({ key }) => {
    next[key] = values[key];
  });
  return next;
};

const validateField = (field: any, value: any, values: Record<string, any> = {}): string => {
  const validations = Array.isArray(field?.validations) ? field.validations : [];
  const type = String(field?.type || 'text').toLowerCase();

  for (const rule of validations) {
    const name = String(rule?.rule || '').toLowerCase();
    const message = getLiteral(rule?.message || 'Valore non valido');

    if (name === 'required') {
      if ((type === 'checkbox' || type === 'toggle' || type === 'switch') && !Boolean(value)) return message;
      if (type === 'select' && field?.multiple && (!Array.isArray(value) || value.length === 0)) return message;
      if ((type === 'tags' || type === 'tags_input') && (!Array.isArray(value) || value.length === 0)) return message;
      if (type === 'editable_list' && (!Array.isArray(value) || value.length === 0)) return message;
      if ((type === 'file' || type === 'attachment' || type === 'audio_recorder') && (!Array.isArray(value) || value.length === 0)) return message;
      if (value == null) return message;
      if (typeof value === 'string' && value.trim().length === 0) return message;
      if (Array.isArray(value) && value.length === 0) return message;
      continue;
    }

    if (name === 'regex') {
      const current = String(value ?? '');
      if (!current) continue;
      try {
        const re = new RegExp(String(rule?.pattern || ''));
        if (!re.test(current)) return message;
      } catch {
        return message;
      }
      continue;
    }

    if (name === 'min_length' || name === 'minlength') {
      const min = Number(rule?.value ?? 0);
      const length = Array.isArray(value) ? value.length : String(value ?? '').length;
      if (length < min) return message;
      continue;
    }

    if (name === 'max_length' || name === 'maxlength') {
      const max = Number(rule?.value ?? Number.MAX_SAFE_INTEGER);
      const length = Array.isArray(value) ? value.length : String(value ?? '').length;
      if (length > max) return message;
      continue;
    }

    if (name === 'equals_field' || name === 'same_as') {
      const otherField = String(rule?.field ?? rule?.value ?? '').trim();
      if (!otherField) continue;
      if (value !== values[otherField]) return message;
      continue;
    }
  }

  return '';
};

export const Form: React.FC<any> = ({
  model = [],
  values: initialValuesProp = {},
  submit_label = 'Submit',
  errors = {},
  action,
  onAction,
  setInput,
  id,
  pendingActions,
  track_loading,
}) => {
  const resolvedInitialValues = React.useMemo(
    () => (
      initialValuesProp && typeof initialValuesProp === 'object' && !Array.isArray(initialValuesProp)
        ? initialValuesProp
        : {}
    ),
    [initialValuesProp],
  );

  const modelNodes = React.useMemo(
    () => mergeInitialValues(model, resolvedInitialValues),
    [model, resolvedInitialValues],
  );
  const fieldEntries = React.useMemo(() => collectFieldEntries(modelNodes), [modelNodes]);

  const [values, setValues] = React.useState<Record<string, any>>(() => buildInitialValues(fieldEntries));
  const [localErrors, setLocalErrors] = React.useState<Record<string, string>>({});
  const [hasSubmitted, setHasSubmitted] = React.useState(false);
  const actionName = getActionName(action);
  const isSubmitLoading = isAnyTrackedActionPending(pendingActions, track_loading, actionName);
  const submitDisabled = isSubmitLoading;

  const modelSignature = React.useMemo(() => buildModelSignature(fieldEntries), [fieldEntries]);
  const appliedSignatureRef = React.useRef<string>('');
  const fieldMap = React.useMemo(() => {
    const map: Record<string, any> = {};
    fieldEntries.forEach(({ key, field }) => {
      map[key] = field;
    });
    return map;
  }, [fieldEntries]);
  const visibleFieldEntries = React.useMemo(
    () => fieldEntries.filter(({ field }) => isFieldVisible(field, values)),
    [fieldEntries, values],
  );

  React.useEffect(() => {
    if (appliedSignatureRef.current === modelSignature) return;

    const initial = buildInitialValues(fieldEntries);
    appliedSignatureRef.current = modelSignature;
    setValues(initial);
    setLocalErrors({});
    setHasSubmitted(false);

    Object.entries(initial).forEach(([key, value]) => {
      setInput?.(key, value);
    });
  }, [fieldEntries, modelSignature, setInput]);

  const updateValue = React.useCallback((key: string, nextValue: any, field?: any) => {
    if (!key) return;
    const normalized = normalizeFieldValue(field || {}, nextValue);
    const nextValues = { ...values, [key]: normalized };

    setValues((prev) => {
      if (valuesEqual(prev[key], normalized)) return prev;
      return { ...prev, [key]: normalized };
    });
    setInput?.(key, normalized);

    if (hasSubmitted) {
      const visibleEntries = fieldEntries.filter(({ field }) => isFieldVisible(field, nextValues));
      const validationErrors = validateAllFields(visibleEntries, nextValues);
      setLocalErrors(validationErrors);
    }
  }, [fieldEntries, hasSubmitted, setInput, values]);

  const setFieldInput = React.useCallback((childId: string, nextValue: any) => {
    const key = String(childId || '');
    if (!key) return;
    const field = fieldMap[key];
    updateValue(key, nextValue, field);
  }, [fieldMap, updateValue]);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setHasSubmitted(true);
    const validationErrors = validateAllFields(visibleFieldEntries, values);

    setLocalErrors(validationErrors);
    if (Object.keys(validationErrors).length > 0) return;

    if (!actionName || !onAction) return;

    const resolvedValues: Record<string, any> = pickVisibleValues(visibleFieldEntries, values);
    const moduleName = inferModuleNameFromAction(action);
    try {
      for (const { key, field } of visibleFieldEntries) {
        const type = String(field?.type || 'text').toLowerCase();
        if (type !== 'file' && type !== 'attachment' && type !== 'audio_recorder') continue;
        const current = resolvedValues[key];
        if (!Array.isArray(current) || current.length === 0) continue;
        resolvedValues[key] = await materializeAttachmentUploads(current, {
          moduleName,
          ingest: field?.ingest !== false,
          actionName,
        });
        setInput?.(key, resolvedValues[key]);
      }
    } catch (uploadError) {
      // eslint-disable-next-line no-console
      console.error('[webclient:forms:form:upload:error]', uploadError);
      return;
    }

    emitActionSpec(action, onAction, {
      ...resolvedValues,
      [id]: {...resolvedValues},
      form_id: id,
    });
  };

  const renderField = (field: any, key: string): React.ReactNode => {
    const type = String(field?.type || 'text').toLowerCase();
    const label = getLiteral(field?.label || key);
    const placeholder = getLiteral(field?.placeholder);
    const options = Array.isArray(field?.options) ? field.options : [];
    const serverErr = getLiteral(errors?.[key] || errors?.[field?.name] || '');
    const err = localErrors[key] || serverErr;
    const value = values[key];

    if (type === 'checkbox') {
      return (
        <Checkbox
          id={key}
          label={label}
          checked={Boolean(value)}
          setInput={setFieldInput}
          syncInitialInput={false}
          error={err}
          onAction={onAction}
          action={field?.action}
        />
      );
    }

    if (type === 'toggle' || type === 'switch') {
      return (
        <Toggle
          id={key}
          label={label}
          checked={Boolean(value)}
          setInput={setFieldInput}
          syncInitialInput={false}
          error={err}
          onAction={onAction}
          action={field?.action}
        />
      );
    }

    if (type === 'textarea') {
      return (
        <TextArea
          id={key}
          label={label}
          value={String(value ?? '')}
          placeholder={placeholder}
          setInput={setFieldInput}
          syncInitialInput={false}
          error={err}
          onAction={onAction}
          action={field?.action}
        />
      );
    }

    if (type === 'radio' || type === 'radio_group') {
      return (
        <RadioGroup
          id={key}
          label={label}
          value={String(value ?? '')}
          options={options}
          setInput={setFieldInput}
          syncInitialInput={false}
          error={err}
          onAction={onAction}
          action={field?.action}
        />
      );
    }

    if (type === 'select') {
      return (
        <Select
          id={key}
          label={label}
          value={field?.multiple ? (Array.isArray(value) ? value : []) : String(value ?? '')}
          options={options}
          placeholder={placeholder || 'Select an option'}
          multiple={Boolean(field?.multiple)}
          setInput={setFieldInput}
          syncInitialInput={false}
          error={err}
          onAction={onAction}
          action={field?.action}
        />
      );
    }

    if (type === 'file' || type === 'attachment') {
      return (
        <Attachment
          id={key}
          label={label}
          value={Array.isArray(value) ? value : []}
          accept={field?.accept}
          multiple={Boolean(field?.multiple)}
          setInput={setFieldInput}
          syncInitialInput={false}
          error={err}
          onAction={onAction}
          action={field?.action}
          ingest={field?.ingest !== false}
          upload_action={field?.action || action}
        />
      );
    }

    if (type === 'audio_recorder') {
      return (
        <AudioRecorder
          id={key}
          label={label}
          value={Array.isArray(value) ? value : []}
          setInput={setFieldInput}
          syncInitialInput={false}
          error={err}
          ingest={field?.ingest !== false}
        />
      );
    }

    if (type === 'tags' || type === 'tags_input') {
      return (
        <TagsInput
          id={key}
          label={label}
          value={Array.isArray(value) ? value : []}
          placeholder={placeholder}
          add_label={field?.add_label}
          item_schema={field?.item_schema}
          setInput={setFieldInput}
          syncInitialInput={false}
          error={err}
          onAction={onAction}
          action={field?.action}
        />
      );
    }

    if (type === 'editable_list') {
      return (
        <EditableList
          id={key}
          item_label={label}
          value={Array.isArray(value) ? value : []}
          placeholder={placeholder}
          add_label={field?.add_label}
          remove_label={field?.remove_label}
          submit_label={field?.submit_label}
          item_schema={field?.item_schema}
          setInput={setFieldInput}
          syncInitialInput={false}
          onAction={onAction}
          action={field?.action}
        />
      );
    }

    if (type === 'date' || type === 'datetime' || type === 'date_time') {
      return (
        <DatePicker
          id={key}
          label={label}
          value={String(value ?? '')}
          min_date={field?.min_date}
          max_date={field?.max_date}
          format={field?.format || (type === 'date' ? 'yyyy-MM-dd' : 'yyyy-MM-dd HH:mm')}
          setInput={setFieldInput}
          syncInitialInput={false}
          error={err}
          onAction={onAction}
          action={field?.action}
        />
      );
    }

    return (
      <TextField
        id={key}
        label={label}
        value={String(value ?? '')}
        placeholder={placeholder}
        password={type === 'password'}
        setInput={setFieldInput}
        syncInitialInput={false}
        error={err}
        onAction={onAction}
        action={field?.action}
      />
    );
  };

  const renderNode = (node: any, path: string): React.ReactNode => {
    if (!node || typeof node !== 'object') return null;

    if (isLayoutNode(node)) {
      const direction = String(node?.type || 'column').toLowerCase();
      const children = getNodeChildren(node);
      if (children.length === 0) return null;
      const renderedChildren = children
        .map((child, index) => ({
          child,
          index,
          node: renderNode(child, `${path}_${index}`),
        }))
        .filter((entry) => entry.node !== null);
      if (renderedChildren.length === 0) return null;

      if (direction === 'row') {
        return (
          <div className="row g-3">
            {renderedChildren.map(({ child, index, node: renderedNode }) => {
              const stretchRaw = Number(child?.stretch ?? child?.span ?? 1);
              const stretch = Number.isFinite(stretchRaw) && stretchRaw > 0 ? stretchRaw : 1;
              return (
                <div key={`${path}_row_${index}`} className="col-12 col-md" style={{ flex: `${stretch} 1 0%` }}>
                  {renderedNode}
                </div>
              );
            })}
          </div>
        );
      }

      return (
        <div className="d-grid gap-3">
          {renderedChildren.map(({ index, node: renderedNode }) => (
            <div key={`${path}_col_${index}`}>{renderedNode}</div>
          ))}
        </div>
      );
    }

    const key = resolveFieldKey(node, `field_${path}`);
    if (!isFieldVisible(node, values)) return null;
    return <div className="a2ui-form-field">{renderField(node, key)}</div>;
  };

  const renderedRootNodes = modelNodes
    .map((node: any, index: number) => ({
      index,
      node: renderNode(node, `node_${index}`),
    }))
    .filter((entry) => entry.node !== null);

  return (
    <form className="a2ui-form" onSubmit={submit}>
      <div className="a2ui-form-body d-grid gap-3">
        {renderedRootNodes.map(({ index, node }) => (
          <div key={`form_node_${index}`}>{node}</div>
        ))}
      </div>
      <div className="a2ui-form-actions mt-4 d-flex justify-content-end">
        <Button type="submit" color="primary" disabled={submitDisabled} className="d-flex align-items-center gap-2">
          {isSubmitLoading && <i className="ri-loader-4-line ri-spin" />}
          {getLiteral(submit_label)}
        </Button>
      </div>
    </form>
  );
};
