import React from 'react';
import {
  Image,
  Keyboard,
  ScrollView,
  StyleSheet,
  Switch,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from 'react-native';
import * as DocumentPicker from 'expo-document-picker';
import { emitActionSpec, getLiteral, parseActionSpec, requestActionConfirm, toBoolean } from '../../shared';
import { Icon } from '../../../components/a2ui/Icon';

type OptionEntry = { id: string; name: string };
type AttachmentEntry = {
  id: string;
  name: string;
  size?: number | null;
  type?: string;
  mimeType?: string;
  uri?: string;
  url?: string;
};

const normalizeModels = (raw: any): OptionEntry[] => {
  if (!Array.isArray(raw)) return [];
  return raw
    .map((item) => {
      if (item && typeof item === 'object') {
        const id = String(item.id ?? item.value ?? '').trim();
        const name = getLiteral(item.name ?? item.label ?? id).trim();
        return id ? { id, name: name || id } : null;
      }
      const id = String(item ?? '').trim();
      return id ? { id, name: id } : null;
    })
    .filter(Boolean) as OptionEntry[];
};

const normalizeList = (raw: any): string[] => {
  if (!Array.isArray(raw)) return [];
  return raw
    .map((item) => {
      if (item && typeof item === 'object') {
        return String(item.id ?? item.name ?? item.value ?? item.label ?? '').trim();
      }
      return String(item ?? '').trim();
    })
    .filter(Boolean);
};

const optionEntriesForFields = (raw: Record<string, any>, fields: any[]): Array<{ key: string; value: any }> => {
  const allowed = new Set(fields.map((field) => String(field?.name ?? '').trim()).filter(Boolean));
  return Object.entries(raw)
    .filter(([key]) => allowed.has(key))
    .map(([key, value]) => ({ key, value }));
};

const formatFileSize = (size: any): string => {
  const value = Number(size || 0);
  if (!Number.isFinite(value) || value <= 0) return '';
  if (value < 1024 * 1024) return `${Math.max(1, Math.round(value / 1024))} KB`;
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
};

const parseOptionValue = (field: any, rawValue: string | boolean) => {
  const type = String(field?.type || '').toLowerCase();
  if (type === 'boolean' || type === 'bool' || type === 'checkbox' || typeof field?.value === 'boolean') {
    return Boolean(rawValue);
  }
  if (rawValue === '') return undefined;
  if (type === 'integer') return Number.parseInt(String(rawValue), 10);
  if (type === 'number') return Number(rawValue);
  return rawValue;
};

const modelSignature = (value: any) => JSON.stringify(normalizeList(value));

export const Composer: React.FC<any> = ({
  id,
  value,
  placeholder,
  action,
  send_action,
  cancel_action,
  on_submit,
  on_stop,
  on_stop_enabled,
  stop_enabled,
  voice,
  voice_action,
  attachment_accept,
  attachment_multiple,
  models,
  model,
  model_editable,
  enable_attachment,
  tools,
  tools_editable,
  skills,
  skills_editable,
  mcp,
  mcp_editable,
  model_capabilities,
  show_capabilities,
  selected_tools,
  selected_skills,
  selected_mcp,
  options,
  options_schema,
  options_editable,
  current_request,
  onAction,
  setInput,
  style,
  disabled,
}) => {
  const [text, setText] = React.useState(getLiteral(value) || '');
  const [attachments, setAttachments] = React.useState<AttachmentEntry[]>([]);
  const [settingsOpen, setSettingsOpen] = React.useState(false);
  const [voiceActive, setVoiceActive] = React.useState(false);

  const modelOptions = React.useMemo(() => normalizeModels(models), [models]);
  const toolOptions = React.useMemo(() => normalizeModels(tools), [tools]);
  const skillOptions = React.useMemo(() => normalizeModels(skills), [skills]);
  const mcpOptions = React.useMemo(() => normalizeModels(mcp), [mcp]);
  const capabilityBadges = React.useMemo(() => normalizeList(model_capabilities), [model_capabilities]);

  const optionFields = React.useMemo(() => (
    options_schema && typeof options_schema === 'object' && Array.isArray(options_schema.fields)
      ? options_schema.fields.filter((field: any) => field && typeof field === 'object' && String(field.name || '').trim())
      : []
  ), [options_schema]);

  const normalizedOptions = React.useMemo(() => {
    const resolved = options && typeof options === 'object' && !Array.isArray(options) ? { ...options } : {};
    optionFields.forEach((field: any) => {
      const name = String(field.name || '').trim();
      if (name && resolved[name] === undefined && field.value !== undefined) resolved[name] = field.value;
    });
    return resolved;
  }, [options, optionFields]);

  const [currentModel, setCurrentModel] = React.useState('');
  const [selectedToolsState, setSelectedToolsState] = React.useState<string[]>(normalizeList(selected_tools));
  const [selectedSkillsState, setSelectedSkillsState] = React.useState<string[]>(normalizeList(selected_skills));
  const [selectedMcpState, setSelectedMcpState] = React.useState<string[]>(normalizeList(selected_mcp));
  const [currentOptions, setCurrentOptions] = React.useState<Record<string, any>>(normalizedOptions);

  React.useEffect(() => {
    setText(getLiteral(value) || '');
  }, [value]);

  React.useEffect(() => {
    const explicit = String(model ?? '').trim();
    if (explicit) {
      setCurrentModel(explicit);
      return;
    }
    setCurrentModel((prev) => (prev && modelOptions.some((entry) => entry.id === prev) ? prev : (modelOptions[0]?.id || '')));
  }, [model, modelOptions]);

  React.useEffect(() => setSelectedToolsState(normalizeList(selected_tools)), [modelSignature(selected_tools)]);
  React.useEffect(() => setSelectedSkillsState(normalizeList(selected_skills)), [modelSignature(selected_skills)]);
  React.useEffect(() => setSelectedMcpState(normalizeList(selected_mcp)), [modelSignature(selected_mcp)]);
  React.useEffect(() => setCurrentOptions(normalizedOptions), [normalizedOptions]);

  const submitAction = on_submit || send_action || action;
  const stopAction = on_stop || on_stop_enabled || cancel_action;
  const interactionAction = action;
  const currentRequest = String(current_request || '').trim();
  const isRunning = Boolean(currentRequest);
  const isDisabled = toBoolean(disabled ?? false);
  const isSubmitDisabled = isDisabled || isRunning;
  const isStopEnabled = toBoolean(stop_enabled ?? (Boolean(stopAction) || isRunning));
  const isAttachmentEnabled = toBoolean(enable_attachment ?? true);
  const isVoiceEnabled = toBoolean(voice ?? true);
  const isModelEditable = toBoolean(model_editable ?? true);
  const areToolsEditable = toBoolean(tools_editable ?? true);
  const areSkillsEditable = toBoolean(skills_editable ?? true);
  const areMcpEditable = toBoolean(mcp_editable ?? true);
  const areOptionsEditable = toBoolean(options_editable ?? false);
  const shouldShowCapabilities = toBoolean(show_capabilities ?? true);

  const attachmentPayload = React.useMemo(() => attachments.map((file) => ({
    name: file.name,
    size: file.size,
    type: file.type || file.mimeType || '',
    mimeType: file.mimeType || file.type || '',
    uri: file.uri,
    url: file.url || file.uri,
  })), [attachments]);

  const buildPayload = React.useCallback((intent: string, extra: Record<string, any> = {}) => ({
    intent,
    component_id: id,
    value: text,
    text,
    model: currentModel,
    selected_tools: selectedToolsState,
    selected_skills: selectedSkillsState,
    selected_mcp: selectedMcpState,
    model_capabilities: capabilityBadges,
    options: optionEntriesForFields(currentOptions, optionFields),
    current_request: currentRequest,
    ...extra,
  }), [id, text, currentModel, selectedToolsState, selectedSkillsState, selectedMcpState, capabilityBadges, currentOptions, optionFields, currentRequest]);

  const emitInteraction = React.useCallback((intent: string, extra: Record<string, any> = {}) => {
    if (!interactionAction || !onAction) return;
    emitActionSpec(interactionAction, onAction, { [id]: buildPayload(intent, extra) });
  }, [id, interactionAction, onAction, buildPayload]);

  const emitInteractionWithoutConfirm = React.useCallback((intent: string, extra: Record<string, any> = {}) => {
    if (!interactionAction || !onAction) return;
    const actionWithoutConfirm = typeof interactionAction === 'object' ? { ...interactionAction, confirm: undefined } : interactionAction;
    emitActionSpec(actionWithoutConfirm, onAction, { [id]: buildPayload(intent, extra) });
  }, [id, interactionAction, onAction, buildPayload]);

  const handleTextChange = (next: string) => {
    setText(next);
    setInput?.(id, next);
  };

  const onSend = async () => {
    if (!text.trim() || !submitAction || !onAction || isSubmitDisabled) return;
    const parsed = parseActionSpec(submitAction);
    if (parsed.confirm && !(await requestActionConfirm(parsed.confirm))) return;
    const actionWithoutConfirm = typeof submitAction === 'object' ? { ...submitAction, confirm: undefined } : submitAction;
    const current = text;
    setText('');
    setInput?.(id, '');
    setAttachments([]);
    emitActionSpec(actionWithoutConfirm, onAction, {
      [id]: {
        intent: 'submit',
        component_id: id,
        text: current,
        attachments: attachmentPayload,
        options: optionEntriesForFields(currentOptions, optionFields),
        selected_tools: selectedToolsState,
        selected_skills: selectedSkillsState,
        selected_mcp: selectedMcpState,
      },
    });
    Keyboard.dismiss();
  };

  const onStop = () => {
    if (!stopAction || !onAction) return;
    emitActionSpec(stopAction, onAction, { [id]: buildPayload('stop') });
  };

  const pickFiles = async () => {
    if (!isAttachmentEnabled || isSubmitDisabled) return;
    const parsed = parseActionSpec(interactionAction);
    if (parsed.confirm && !(await requestActionConfirm(parsed.confirm))) return;
    const result = await DocumentPicker.getDocumentAsync({
      type: getLiteral(attachment_accept || '*/*') || '*/*',
      multiple: toBoolean(attachment_multiple ?? true),
      copyToCacheDirectory: true,
    });
    if (result.canceled) return;
    const picked = result.assets.map((asset) => ({
      id: `${asset.name}_${asset.size || 0}_${Math.random().toString(36).slice(2, 8)}`,
      name: asset.name,
      size: asset.size,
      type: asset.mimeType || '',
      mimeType: asset.mimeType || '',
      uri: asset.uri,
      url: asset.uri,
    }));
    const next = toBoolean(attachment_multiple ?? true) ? [...attachments, ...picked] : picked.slice(0, 1);
    setAttachments(next);
    emitInteractionWithoutConfirm('attachment_add', {
      attachments: next.map((file) => ({
        name: file.name,
        size: file.size,
        type: file.type || file.mimeType || '',
        mimeType: file.mimeType || file.type || '',
        uri: file.uri,
        url: file.url || file.uri,
      })),
    });
  };

  const removeAttachment = async (fileId: string) => {
    const parsed = parseActionSpec(interactionAction);
    if (parsed.confirm && !(await requestActionConfirm(parsed.confirm))) return;
    const next = attachments.filter((file) => file.id !== fileId);
    setAttachments(next);
    emitInteractionWithoutConfirm('attachment_remove', { attachments: next });
  };

  const updateOption = (field: any, rawValue: string | boolean) => {
    const name = String(field?.name || '').trim();
    if (!name) return;
    setCurrentOptions((prev) => {
      const next = { ...prev };
      const parsed = parseOptionValue(field, rawValue);
      if (parsed === undefined) delete next[name];
      else next[name] = parsed;
      return next;
    });
  };

  const toggleSelection = (
    valueToToggle: string,
    current: string[],
    setCurrent: React.Dispatch<React.SetStateAction<string[]>>,
    intent: string,
  ) => {
    const next = current.includes(valueToToggle)
      ? current.filter((entry) => entry !== valueToToggle)
      : [...current, valueToToggle];
    setCurrent(next);
    emitInteraction(intent, {
      selected_tools: intent === 'tools_change' ? next : selectedToolsState,
      selected_skills: intent === 'skills_change' ? next : selectedSkillsState,
      selected_mcp: intent === 'mcp_change' ? next : selectedMcpState,
    });
  };

  const onPickModel = (nextModel: string) => {
    if (isDisabled || !isModelEditable || isRunning) return;
    setCurrentModel(nextModel);
    emitInteraction('model_change', { model: nextModel });
  };

  const toggleVoice = () => {
    if (isSubmitDisabled) return;
    const next = !voiceActive;
    setVoiceActive(next);
    const targetAction = voice_action || interactionAction;
    if (targetAction && onAction) {
      emitActionSpec(targetAction, onAction, { [id]: buildPayload('voice_toggle', { voice_active: next }) });
    }
  };

  const hasSettings = modelOptions.length > 0
    || toolOptions.length > 0
    || skillOptions.length > 0
    || mcpOptions.length > 0
    || (areOptionsEditable && optionFields.length > 0);

  return (
    <View style={[styles.container, style]}>
      {shouldShowCapabilities && capabilityBadges.length > 0 ? (
        <View style={styles.capabilityWrap}>
          {capabilityBadges.map((cap) => <Text key={`${id}_cap_${cap}`} style={styles.capabilityChip}>{cap}</Text>)}
        </View>
      ) : null}

      {attachments.length > 0 ? (
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.attachments}>
          {attachments.map((file) => {
            const isImage = String(file.type || file.mimeType || '').startsWith('image/') || /\.(png|jpe?g|gif|webp)$/i.test(file.name);
            const source = file.url || file.uri;
            return (
              <View key={file.id} style={styles.attachmentCard}>
                <View style={styles.attachmentPreview}>
                  {isImage && source ? (
                    <Image source={{ uri: source }} style={styles.attachmentImage} />
                  ) : (
                    <Icon name="ri-file-text-line" size={20} color="#8B949E" />
                  )}
                </View>
                <View style={styles.attachmentText}>
                  <Text style={styles.attachmentName} numberOfLines={1}>{file.name}</Text>
                  <Text style={styles.attachmentSize} numberOfLines={1}>{formatFileSize(file.size)}</Text>
                </View>
                <TouchableOpacity style={styles.attachmentRemove} onPress={() => removeAttachment(file.id)}>
                  <Icon name="ri-close-line" size={14} color="#E6EDF3" />
                </TouchableOpacity>
              </View>
            );
          })}
        </ScrollView>
      ) : null}

      {settingsOpen && hasSettings ? (
        <View style={styles.settingsPanel}>
          {modelOptions.length > 0 ? (
            <View style={styles.settingBlock}>
              <Text style={styles.settingTitle}>Model</Text>
              <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.chipRow}>
                {modelOptions.map((entry) => (
                  <TouchableOpacity
                    key={`${id}_model_${entry.id}`}
                    style={[styles.choiceChip, currentModel === entry.id && styles.choiceChipActive]}
                    onPress={() => onPickModel(entry.id)}
                    disabled={isDisabled || !isModelEditable || isRunning}
                  >
                    <Text style={[styles.choiceText, currentModel === entry.id && styles.choiceTextActive]} numberOfLines={1}>{entry.name}</Text>
                  </TouchableOpacity>
                ))}
              </ScrollView>
            </View>
          ) : null}

          {areOptionsEditable && optionFields.length > 0 ? (
            <View style={styles.settingBlock}>
              <Text style={styles.settingTitle}>Options</Text>
              {optionFields.map((field: any) => {
                const name = String(field.name || '').trim();
                const label = getLiteral(field.label || name);
                const value = currentOptions[name];
                const isBoolean = ['boolean', 'bool', 'checkbox'].includes(String(field.type || '').toLowerCase()) || typeof value === 'boolean' || typeof field.value === 'boolean';
                return (
                  <View key={`${id}_option_${name}`} style={styles.optionRow}>
                    <Text style={styles.optionLabel} numberOfLines={1}>{label}</Text>
                    {isBoolean ? (
                      <Switch
                        value={toBoolean(value)}
                        onValueChange={(next) => updateOption(field, next)}
                        trackColor={{ false: '#30363D', true: '#1F6FEB' }}
                        thumbColor="#E6EDF3"
                      />
                    ) : (
                      <TextInput
                        style={styles.optionInput}
                        value={value == null ? '' : String(value)}
                        onChangeText={(next) => updateOption(field, next)}
                        keyboardType={['number', 'integer'].includes(String(field.type || '').toLowerCase()) ? 'numeric' : 'default'}
                        placeholderTextColor="#6E7681"
                      />
                    )}
                  </View>
                );
              })}
            </View>
          ) : null}

          {areToolsEditable && toolOptions.length > 0 ? (
            <ChoiceGroup
              title="Tools"
              id={id}
              prefix="tool"
              options={toolOptions}
              selected={selectedToolsState}
              onToggle={(entry) => toggleSelection(entry, selectedToolsState, setSelectedToolsState, 'tools_change')}
            />
          ) : null}
          {areSkillsEditable && skillOptions.length > 0 ? (
            <ChoiceGroup
              title="Skills"
              id={id}
              prefix="skill"
              options={skillOptions}
              selected={selectedSkillsState}
              onToggle={(entry) => toggleSelection(entry, selectedSkillsState, setSelectedSkillsState, 'skills_change')}
            />
          ) : null}
          {areMcpEditable && mcpOptions.length > 0 ? (
            <ChoiceGroup
              title="MCP"
              id={id}
              prefix="mcp"
              options={mcpOptions}
              selected={selectedMcpState}
              onToggle={(entry) => toggleSelection(entry, selectedMcpState, setSelectedMcpState, 'mcp_change')}
            />
          ) : null}
        </View>
      ) : null}

      <View style={styles.inputShell}>
        <TextInput
          style={styles.input}
          placeholder={getLiteral(placeholder) || 'Type a message...'}
          value={text}
          onChangeText={handleTextChange}
          multiline
          editable={!isSubmitDisabled}
          placeholderTextColor="#6E7681"
          textAlignVertical="top"
        />
        <View style={styles.toolbar}>
          {hasSettings ? (
            <TouchableOpacity
              style={[styles.iconButton, settingsOpen && styles.iconButtonActive]}
              onPress={() => setSettingsOpen((prev) => !prev)}
              disabled={isSubmitDisabled}
            >
              <Icon name="ri-settings-3-line" size={19} color={settingsOpen ? '#FFFFFF' : '#8B949E'} />
            </TouchableOpacity>
          ) : null}
          {isAttachmentEnabled ? (
            <TouchableOpacity style={styles.iconButton} onPress={pickFiles} disabled={isSubmitDisabled}>
              <Icon name="ri-attachment-2" size={19} color="#8B949E" />
            </TouchableOpacity>
          ) : null}
          {isVoiceEnabled ? (
            <TouchableOpacity style={[styles.iconButton, voiceActive && styles.dangerButton]} onPress={toggleVoice} disabled={isSubmitDisabled}>
              <Icon name={voiceActive ? 'ri-mic-off-line' : 'ri-mic-line'} size={19} color={voiceActive ? '#FFFFFF' : '#8B949E'} />
            </TouchableOpacity>
          ) : null}
          {isStopEnabled && stopAction ? (
            <TouchableOpacity style={styles.iconButton} onPress={onStop} disabled={!currentRequest && !isRunning}>
              <Icon name="ri-stop-fill" size={18} color={currentRequest || isRunning ? '#F85149' : '#484F58'} />
            </TouchableOpacity>
          ) : null}
          <TouchableOpacity
            style={[styles.sendButton, (!text.trim() || isSubmitDisabled) && styles.sendButtonDisabled]}
            onPress={onSend}
            disabled={!text.trim() || isSubmitDisabled}
          >
            <Icon name="ri-send-plane-2-fill" size={19} color="#FFFFFF" />
          </TouchableOpacity>
        </View>
      </View>
    </View>
  );
};

const ChoiceGroup: React.FC<{
  title: string;
  id: string;
  prefix: string;
  options: OptionEntry[];
  selected: string[];
  onToggle: (value: string) => void;
}> = ({ title, id, prefix, options, selected, onToggle }) => (
  <View style={styles.settingBlock}>
    <Text style={styles.settingTitle}>{title}</Text>
    <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.chipRow}>
      {options.map((entry) => {
        const active = selected.includes(entry.id);
        return (
          <TouchableOpacity
            key={`${id}_${prefix}_${entry.id}`}
            style={[styles.choiceChip, active && styles.choiceChipActive]}
            onPress={() => onToggle(entry.id)}
          >
            <Text style={[styles.choiceText, active && styles.choiceTextActive]} numberOfLines={1}>{entry.name}</Text>
          </TouchableOpacity>
        );
      })}
    </ScrollView>
  </View>
);

const styles = StyleSheet.create({
  container: {
    width: '100%',
    backgroundColor: '#0D1117',
    borderTopWidth: 1,
    borderColor: '#30363D',
    paddingHorizontal: 10,
    paddingTop: 8,
    paddingBottom: 10,
    gap: 8,
  },
  capabilityWrap: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 6,
  },
  capabilityChip: {
    color: '#C9D1D9',
    backgroundColor: '#21262D',
    borderWidth: 1,
    borderColor: '#30363D',
    borderRadius: 999,
    paddingHorizontal: 8,
    paddingVertical: 3,
    fontSize: 11,
    fontWeight: '600',
  },
  attachments: {
    gap: 8,
    paddingRight: 12,
  },
  attachmentCard: {
    width: 176,
    minHeight: 52,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    backgroundColor: '#161B22',
    borderWidth: 1,
    borderColor: '#30363D',
    borderRadius: 8,
    padding: 6,
  },
  attachmentPreview: {
    width: 40,
    height: 40,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: 6,
    backgroundColor: '#0D1117',
    overflow: 'hidden',
  },
  attachmentImage: {
    width: '100%',
    height: '100%',
    resizeMode: 'cover',
  },
  attachmentText: {
    flex: 1,
    minWidth: 0,
  },
  attachmentName: {
    color: '#E6EDF3',
    fontSize: 12,
    fontWeight: '600',
  },
  attachmentSize: {
    color: '#8B949E',
    fontSize: 10,
    marginTop: 2,
  },
  attachmentRemove: {
    width: 24,
    height: 24,
    borderRadius: 12,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#30363D',
  },
  settingsPanel: {
    borderWidth: 1,
    borderColor: '#30363D',
    borderRadius: 8,
    backgroundColor: '#161B22',
    padding: 10,
    gap: 10,
  },
  settingBlock: {
    gap: 6,
  },
  settingTitle: {
    color: '#8B949E',
    fontSize: 11,
    fontWeight: '700',
    textTransform: 'uppercase',
  },
  chipRow: {
    gap: 6,
    paddingRight: 8,
  },
  choiceChip: {
    maxWidth: 180,
    borderWidth: 1,
    borderColor: '#30363D',
    borderRadius: 999,
    paddingHorizontal: 10,
    paddingVertical: 6,
    backgroundColor: '#0D1117',
  },
  choiceChipActive: {
    borderColor: '#58A6FF',
    backgroundColor: '#1F6FEB33',
  },
  choiceText: {
    color: '#C9D1D9',
    fontSize: 12,
    fontWeight: '600',
  },
  choiceTextActive: {
    color: '#FFFFFF',
  },
  optionRow: {
    minHeight: 38,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 10,
  },
  optionLabel: {
    flex: 1,
    color: '#C9D1D9',
    fontSize: 12,
    fontWeight: '600',
  },
  optionInput: {
    width: 132,
    height: 34,
    borderWidth: 1,
    borderColor: '#30363D',
    borderRadius: 6,
    paddingHorizontal: 8,
    color: '#E6EDF3',
    backgroundColor: '#0D1117',
    fontSize: 12,
  },
  inputShell: {
    flexDirection: 'column',
    alignItems: 'stretch',
    gap: 8,
    borderWidth: 1,
    borderColor: '#30363D',
    borderRadius: 14,
    backgroundColor: '#161B22',
    padding: 8,
  },
  input: {
    width: '100%',
    minHeight: 40,
    maxHeight: 132,
    color: '#E6EDF3',
    fontSize: 15,
    lineHeight: 20,
    paddingTop: 8,
    paddingBottom: 8,
    paddingHorizontal: 4,
  },
  toolbar: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'flex-start',
    gap: 6,
    width: '100%',
  },
  iconButton: {
    width: 34,
    height: 34,
    borderRadius: 8,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#0D1117',
    borderWidth: 1,
    borderColor: '#30363D',
  },
  iconButtonActive: {
    backgroundColor: '#1F6FEB',
    borderColor: '#58A6FF',
  },
  dangerButton: {
    backgroundColor: '#DA3633',
    borderColor: '#F85149',
  },
  sendButton: {
    marginLeft: 'auto',
    width: 34,
    height: 34,
    borderRadius: 8,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#238636',
  },
  sendButtonDisabled: {
    opacity: 0.45,
    backgroundColor: '#30363D',
  },
});
