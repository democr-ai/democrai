import React from 'react';
import { View, Text, StyleSheet, TouchableOpacity, ActivityIndicator } from 'react-native';
import { TextField } from './text_field';
import { TextArea } from './textarea';
import { Checkbox } from './checkbox';
import { RadioGroup } from './radio_group';
import { Select } from './select';
import { Attachment } from './attachment';
import { Toggle } from './toggle';
import { TagsInput } from './tags_input';
import { EditableList } from './editable_list';
import { AudioRecorder } from './audio_recorder';
import { getLiteral, emitActionSpec, isAnyTrackedActionPending } from '../../shared';
import { evaluateRule } from '../../rules';
import { inferModuleNameFromAction, materializeAttachmentUploads } from '../../../utils/uploads';

const isLayoutNode = (node: any): boolean => {
  const t = String(node?.type || '').toLowerCase();
  return t === 'row' || t === 'column';
};

const getNodeChildren = (node: any): any[] => {
  const children = node?.children ?? node?.items ?? [];
  return Array.isArray(children) ? children.filter((child: any) => child && typeof child === 'object') : [];
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
  if (type === 'tags' || type === 'tags_input' || type === 'tagsinput') return Array.isArray(raw) ? raw : [];
  if (type === 'editable_list' || type === 'editablelist') return Array.isArray(raw) ? raw : [];
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
  if (type === 'tags' || type === 'tags_input' || type === 'tagsinput') return Array.isArray(value) ? value : [];
  if (type === 'editable_list' || type === 'editablelist') return Array.isArray(value) ? value : [];
  if (type === 'file' || type === 'attachment' || type === 'audio_recorder') return Array.isArray(value) ? value : [];
  return value ?? '';
};

const valuesEqual = (left: any, right: any): boolean => JSON.stringify(left) === JSON.stringify(right);

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
  .map(({ key, field }) => `${key}:${String(field?.type || 'text')}:${JSON.stringify(normalizeInitialValue(field))}`)
  .join('|');

const buildFieldShapeSignature = (entries: FieldEntry[]): string => entries
  .map(({ key, field }) => `${key}:${String(field?.type || 'text')}`)
  .join('|');

const buildRuleOptions = (
  values: Record<string, any>,
  surfaceModel?: any,
  stateModel?: any,
) => ({
  surfaceModel: surfaceModel && typeof surfaceModel === 'object' ? { ...surfaceModel, ...values } : values,
  stateModel,
  formValues: values,
});

const isFieldVisible = (field: any, values: Record<string, any>, surfaceModel?: any, stateModel?: any): boolean => {
  const options = buildRuleOptions(values, surfaceModel, stateModel);
  if (field?.show_if !== undefined && !evaluateRule(field.show_if, options, true)) return false;
  if (field?.hide_if !== undefined && evaluateRule(field.hide_if, options, false)) return false;
  return true;
};

const validateField = (field: any, value: any, values: Record<string, any> = {}): string => {
  const validations = Array.isArray(field?.validations) ? field.validations : [];
  const type = String(field?.type || 'text').toLowerCase();

  for (const rule of validations) {
    const name = String(rule?.rule || '').toLowerCase();
    const message = getLiteral(rule?.message || 'Invalid value');

    if (name === 'required') {
      if ((type === 'checkbox' || type === 'toggle' || type === 'switch') && !Boolean(value)) return message;
      if (type === 'select' && field?.multiple && (!Array.isArray(value) || value.length === 0)) return message;
      if ((type === 'file' || type === 'attachment') && (!Array.isArray(value) || value.length === 0)) return message;
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
      if (otherField && value !== values[otherField]) return message;
    }
  }

  return '';
};

const validateAllFields = (entries: FieldEntry[], values: Record<string, any>): Record<string, string> => {
  const nextErrors: Record<string, string> = {};
  entries.forEach(({ key, field }) => {
    const err = validateField(field, values[key], values);
    if (err) nextErrors[key] = err;
  });
  return nextErrors;
};

const pickVisibleValues = (
  entries: FieldEntry[],
  values: Record<string, any>,
  surfaceModel?: any,
  stateModel?: any,
): Record<string, any> => {
  const next: Record<string, any> = {};
  entries.forEach(({ key, field }) => {
    if (!isFieldVisible(field, values, surfaceModel, stateModel)) return;
    next[key] = values[key];
  });
  return next;
};

export const Form: React.FC<any> = ({
  model = [],
  values: initialValuesProp = {},
  submit_label = 'Submit',
  errors = {},
  action,
  params = {},
  onAction,
  setInput,
  id,
  pendingActions,
  track_loading,
  dataModel,
  stateModel,
  surfaceId,
  jwt,
}) => {
  const surfaceModel = surfaceId ? dataModel?.[surfaceId] : undefined;
  const resolvedInitialValues = React.useMemo(
    () => (initialValuesProp && typeof initialValuesProp === 'object' && !Array.isArray(initialValuesProp) ? initialValuesProp : {}),
    [initialValuesProp],
  );
  const modelNodes = React.useMemo(
    () => {
      const nodes = Array.isArray(model) ? model.filter((node) => node && typeof node === 'object') : [];
      if (Object.keys(resolvedInitialValues).length === 0) return nodes;
      const apply = (node: any): any => {
        if (!node || typeof node !== 'object') return node;
        const next = { ...node };
        if (isLayoutNode(next)) {
          if (Array.isArray(next.children)) next.children = next.children.map((child: any) => apply(child));
          if (Array.isArray(next.items)) next.items = next.items.map((child: any) => apply(child));
          return next;
        }
        const name = String(next?.name || '').trim();
        if (name && Object.prototype.hasOwnProperty.call(resolvedInitialValues, name)) next.value = resolvedInitialValues[name];
        return next;
      };
      return nodes.map((node) => apply(node));
    },
    [model, resolvedInitialValues],
  );
  const fieldEntries = React.useMemo(() => collectFieldEntries(modelNodes), [modelNodes]);

  const [values, setValues] = React.useState<Record<string, any>>(() => buildInitialValues(fieldEntries));
  const [localErrors, setLocalErrors] = React.useState<Record<string, string>>({});
  const [hasSubmitted, setHasSubmitted] = React.useState(false);
  const actionName = getActionName(action);
  const isSubmitLoading = isAnyTrackedActionPending(pendingActions, track_loading, actionName);
  const modelSignature = React.useMemo(() => buildModelSignature(fieldEntries), [fieldEntries]);
  const fieldShapeSignature = React.useMemo(() => buildFieldShapeSignature(fieldEntries), [fieldEntries]);
  const appliedSignatureRef = React.useRef('');
  const appliedShapeSignatureRef = React.useRef('');
  const fieldMap = React.useMemo(() => {
    const map: Record<string, any> = {};
    fieldEntries.forEach(({ key, field }) => {
      map[key] = field;
    });
    return map;
  }, [fieldEntries]);
  const visibleFieldEntries = React.useMemo(
    () => fieldEntries.filter(({ field }) => isFieldVisible(field, values, surfaceModel, stateModel)),
    [fieldEntries, surfaceModel, stateModel, values],
  );

  React.useEffect(() => {
    if (appliedSignatureRef.current === modelSignature) return;
    const initial = buildInitialValues(fieldEntries);
    const shapeChanged = appliedShapeSignatureRef.current !== fieldShapeSignature;
    appliedSignatureRef.current = modelSignature;
    appliedShapeSignatureRef.current = fieldShapeSignature;
    setValues((prev) => {
      if (shapeChanged) return initial;
      return {
        ...initial,
        ...Object.fromEntries(Object.entries(prev).filter(([key]) => Object.prototype.hasOwnProperty.call(initial, key))),
      };
    });
    if (shapeChanged) {
      setLocalErrors({});
      setHasSubmitted(false);
      Object.entries(initial).forEach(([key, value]) => setInput?.(key, value));
    }
  }, [fieldEntries, fieldShapeSignature, modelSignature, setInput]);

  const setFieldInput = (childId: string, nextValue: any, publishGlobal = true) => {
    const key = String(childId || '');
    if (!key) return;
    const field = fieldMap[key] || {};
    const normalized = normalizeFieldValue(field, nextValue);
    const nextValues = { ...values, [key]: normalized };
    setValues((prev) => (valuesEqual(prev[key], normalized) ? prev : { ...prev, [key]: normalized }));
    if (publishGlobal) setInput?.(key, normalized);
    if (hasSubmitted) {
      setLocalErrors(validateAllFields(
        fieldEntries.filter(({ field }) => isFieldVisible(field, nextValues, surfaceModel, stateModel)),
        nextValues,
      ));
    }
  };

  const submit = async () => {
    setHasSubmitted(true);
    const validationErrors = validateAllFields(visibleFieldEntries, values);
    setLocalErrors(validationErrors);
    if (Object.keys(validationErrors).length > 0) return;
    if (!actionName || !onAction) return;

    const resolvedValues = pickVisibleValues(visibleFieldEntries, values, surfaceModel, stateModel);
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
          jwt,
          actionName,
        });
        setInput?.(key, resolvedValues[key]);
      }
    } catch (uploadError) {
      console.error('[reactnative:forms:form:upload:error]', uploadError);
      return;
    }

    emitActionSpec(action, onAction, {
      ...(params && typeof params === 'object' && !Array.isArray(params) ? params : {}),
      ...resolvedValues,
      [id]: { ...resolvedValues },
      form_id: id,
    });
  };

  const renderField = (field: any, key: string) => {
    const type = String(field?.type || 'text').toLowerCase();
    const label = getLiteral(field?.label || key);
    const placeholder = getLiteral(field?.placeholder);
    const options = Array.isArray(field?.options) ? field.options : [];
    const serverErr = getLiteral(errors?.[key] || errors?.[field?.name] || '');
    const err = localErrors[key] || serverErr;
    const value = values[key];

    if (!isFieldVisible(field, values, surfaceModel, stateModel)) return null;

    const commonProps = {
      id: key,
      label,
      value,
      setInput: setFieldInput,
      error: err,
      onAction,
      action: field?.action,
    };

    switch (type) {
      case 'checkbox':
        return <Checkbox {...commonProps} checked={Boolean(value)} />;
      case 'toggle':
      case 'switch':
        return <Toggle {...commonProps} checked={Boolean(value)} />;
      case 'textarea':
        return <TextArea {...commonProps} />;
      case 'radio':
      case 'radio_group':
        return <RadioGroup {...commonProps} options={options} />;
      case 'select':
        return (
          <Select 
            {...commonProps} 
            options={options} 
            placeholder={placeholder} 
            multiple={Boolean(field?.multiple)} 
          />
        );
      case 'tags':
      case 'tags_input':
      case 'tagsinput':
        return (
          <TagsInput
            {...commonProps}
            value={Array.isArray(value) ? value : []}
            placeholder={placeholder}
            add_label={field?.add_label ?? field?.addLabel}
            item_schema={field?.item_schema ?? field?.itemSchema}
            params={field?.params ?? field?.context}
            action={undefined}
            onAction={undefined}
            setInput={(childId: string, nextValue: any) => setFieldInput(childId, nextValue, false)}
            syncInitialInput={false}
          />
        );
      case 'editable_list':
      case 'editablelist':
        return (
          <EditableList
            id={key}
            item_label={label}
            value={Array.isArray(value) ? value : []}
            placeholder={placeholder}
            add_label={field?.add_label ?? field?.addLabel}
            remove_label={field?.remove_label ?? field?.removeLabel}
            submit_label={field?.submit_label ?? field?.submitLabel}
            item_schema={field?.item_schema ?? field?.itemSchema}
            params={field?.params ?? field?.context}
            action={field?.action}
            onAction={onAction}
            setInput={(childId: string, nextValue: any) => setFieldInput(childId, nextValue, false)}
            syncInitialInput={false}
            pendingActions={pendingActions}
          />
        );
      case 'file':
      case 'attachment':
        return (
          <Attachment
            {...commonProps} 
            accept={field?.accept} 
            multiple={Boolean(field?.multiple)} 
          />
        );
      case 'audio_recorder':
        return (
          <AudioRecorder
            {...commonProps}
            value={Array.isArray(value) ? value : []}
            multiple={field?.multiple !== false}
          />
        );
      case 'password':
        return (
          <TextField
            {...commonProps}
            password
            autoCapitalize={field?.autoCapitalize ?? field?.autocapitalize}
          />
        );
      default:
        return (
          <TextField
            {...commonProps}
            placeholder={placeholder}
            autoCapitalize={field?.autoCapitalize ?? field?.autocapitalize}
            keyboardType={type === 'email' ? 'email-address' : undefined}
          />
        );
    }
  };

  const renderNode = (node: any, path: string): React.ReactNode => {
    if (!node || typeof node !== 'object') return null;

    if (isLayoutNode(node)) {
      const children = getNodeChildren(node);
      return (
        <View style={styles.layoutNode}>
          {children.map((child, index) => (
            <View key={`${path}_${index}`} style={styles.childNode}>
              {renderNode(child, `${path}_${index}`)}
            </View>
          ))}
        </View>
      );
    }

    const key = resolveFieldKey(node, `field_${path}`);
    return renderField(node, key);
  };

  return (
    <View style={styles.container}>
      {modelNodes.map((node, index) => (
        <View key={`node_${index}`} style={styles.nodeWrapper}>
          {renderNode(node, `node_${index}`)}
        </View>
      ))}
      <TouchableOpacity 
        style={[
          styles.submitBtn, 
          isSubmitLoading && styles.submitBtnDisabled
        ]} 
        onPress={submit}
        disabled={isSubmitLoading}
      >
        {isSubmitLoading ? <ActivityIndicator color="#fff" style={styles.submitSpinner} /> : null}
        <Text style={styles.submitText}>{getLiteral(submit_label)}</Text>
      </TouchableOpacity>
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    width: '100%',
  },
  nodeWrapper: {
    marginBottom: 12,
  },
  layoutNode: {
    gap: 12,
  },
  childNode: {
    width: '100%',
  },
  submitBtn: {
    backgroundColor: '#3b82f6',
    paddingVertical: 12,
    borderRadius: 8,
    alignItems: 'center',
    justifyContent: 'center',
    flexDirection: 'row',
    marginTop: 16,
  },
  submitBtnDisabled: {
    opacity: 0.6,
  },
  submitText: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '600',
  },
  submitSpinner: {
    marginRight: 8,
  },
});
