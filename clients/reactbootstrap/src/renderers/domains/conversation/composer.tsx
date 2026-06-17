import React from 'react';
import { parseStyle } from '@/utils/style';
import { emitActionSpec, getLiteral, parseActionSpec, requestActionConfirm, toBoolean } from '@/renderers/shared';
import { 
  Button, 
  Badge, 
  Input, 
  Label,
} from 'design-react-kit';
import { DropdownItem, UncontrolledDropdown, DropdownToggle, DropdownMenu } from 'reactstrap';
import { AudioRecordingController, startBrowserAudioRecording } from '@/utils/audioRecording';
import { inferActionName, inferModuleNameFromAction, uploadBrowserFile, uploadBrowserFiles } from '@/utils/uploads';
import { cn } from '@/lib/utils';

const normalizeModels = (raw: any): Array<{ id: string; name: string }> => {
  if (!Array.isArray(raw)) return [];
  return raw
    .map((item) => {
      if (item && typeof item === 'object') {
        const id = String(item.id ?? item.value ?? '').trim();
        const name = String(item.name ?? item.label ?? id).trim();
        return id ? { id, name: name || id } : null;
      }
      const id = String(item ?? '').trim();
      return id ? { id, name: id } : null;
    })
    .filter(Boolean) as Array<{ id: string; name: string }>;
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

const optionEntries = (raw: Record<string, any>): Array<{ key: string; value: any }> => (
  Object.entries(raw).map(([key, value]) => ({ key, value }))
);

const optionEntriesForFields = (
  raw: Record<string, any>,
  fields: any[],
): Array<{ key: string; value: any }> => {
  const allowed = new Set(
    fields
      .map((field) => String(field?.name ?? '').trim())
      .filter(Boolean),
  );
  return optionEntries(raw).filter((entry) => allowed.has(entry.key));
};

const filePreview = (file: { name: string; url: string; type: string }) => {
  const lower = String(file.name || '').toLowerCase();
  if (String(file.type || '').startsWith('image/') || /\.(png|jpe?g|gif|webp|svg)$/.test(lower)) {
    return <img src={file.url} alt={file.name} className="h-100 w-100 rounded object-cover" />;
  }
  if (file.type === 'application/pdf' || lower.endsWith('.pdf')) {
    return <span className="xsmall fw-bold text-muted">PDF</span>;
  }
  return <i className="ri-file-text-line text-muted" />;
};

const matchesAccept = (file: File, accept: string): boolean => {
  const patterns = String(accept || '')
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean);
  if (!patterns.length) return true;
  return patterns.some((pattern) => {
    if (pattern.endsWith('/*')) return file.type.startsWith(pattern.slice(0, -1));
    if (pattern.startsWith('.')) return file.name.toLowerCase().endsWith(pattern.toLowerCase());
    return file.type === pattern;
  });
};

const clipboardImageName = (file: File): string => {
  const extension = file.type === 'image/jpeg'
    ? 'jpg'
    : String(file.type || '').split('/')[1] || 'png';
  const stamp = new Date().toISOString().replace(/[-:]/g, '').replace(/\..+$/, '').replace('T', '-');
  return `clipboard-image-${stamp}.${extension}`;
};

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
  ingest = true,
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
  const [voiceActive, setVoiceActive] = React.useState(false);
  const [voiceTranscribing, setVoiceTranscribing] = React.useState(false);
  const [attachments, setAttachments] = React.useState<
    Array<{ id: string; file?: File; name: string; size: number; type: string; url: string }>
  >([]);
  const fileInputRef = React.useRef<HTMLInputElement>(null);
  const audioRecordingRef = React.useRef<AudioRecordingController | null>(null);

  const modelOptions = React.useMemo(() => normalizeModels(models), [models]);
  const toolOptions = React.useMemo(() => normalizeModels(tools), [tools]);
  const skillOptions = React.useMemo(() => normalizeModels(skills), [skills]);
  const mcpOptions = React.useMemo(() => normalizeModels(mcp), [mcp]);

  const capabilityBadges = React.useMemo(
    () => normalizeList(model_capabilities),
    [model_capabilities],
  );

  const [currentModel, setCurrentModel] = React.useState<string>('');
  const currentModelLabel = React.useMemo(
    () => modelOptions.find((modelOption) => modelOption.id === currentModel)?.name || currentModel,
    [currentModel, modelOptions],
  );
  const [selectedToolsState, setSelectedToolsState] = React.useState<string[]>(
    normalizeList(selected_tools),
  );
  const [selectedSkillsState, setSelectedSkillsState] = React.useState<string[]>(
    normalizeList(selected_skills),
  );
  const [selectedMcpState, setSelectedMcpState] = React.useState<string[]>(
    normalizeList(selected_mcp),
  );
  const selectedToolsPropKey = React.useMemo(
    () => JSON.stringify(normalizeList(selected_tools)),
    [selected_tools],
  );
  const selectedSkillsPropKey = React.useMemo(
    () => JSON.stringify(normalizeList(selected_skills)),
    [selected_skills],
  );
  const selectedMcpPropKey = React.useMemo(
    () => JSON.stringify(normalizeList(selected_mcp)),
    [selected_mcp],
  );
  const optionFields = React.useMemo(() => {
    const schemaFields = (
      options_schema && typeof options_schema === 'object' && Array.isArray(options_schema.fields)
        ? options_schema.fields.filter((field: any) => field && typeof field === 'object' && String(field.name || '').trim())
        : []
    );
    return schemaFields;
  }, [options_schema]);
  const normalizedOptions = React.useMemo(() => {
    const resolved = options && typeof options === 'object' && !Array.isArray(options) ? { ...options } : {};
    optionFields.forEach((field: any) => {
      const name = String(field.name || '').trim();
      if (name && resolved[name] === undefined && field.value !== undefined) {
        resolved[name] = field.value;
      }
    });
    return resolved;
  }, [options, optionFields]);
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
    if (!modelOptions.length) {
      setCurrentModel('');
      return;
    }
    setCurrentModel((prev) => (prev && modelOptions.some((m) => m.id === prev) ? prev : modelOptions[0].id));
  }, [model, modelOptions]);

  React.useEffect(() => {
    setSelectedToolsState(normalizeList(selected_tools));
  }, [selectedToolsPropKey]);

  React.useEffect(() => {
    setSelectedSkillsState(normalizeList(selected_skills));
  }, [selectedSkillsPropKey]);

  React.useEffect(() => {
    setSelectedMcpState(normalizeList(selected_mcp));
  }, [selectedMcpPropKey]);

  React.useEffect(() => {
    setCurrentOptions(normalizedOptions);
  }, [normalizedOptions]);

  React.useEffect(() => () => {
    attachments.forEach((item) => {
      if (item.url.startsWith('blob:')) URL.revokeObjectURL(item.url);
    });
    audioRecordingRef.current?.cancel();
  }, [attachments]);

  const submitAction = on_submit || send_action;
  const stopAction = on_stop || on_stop_enabled || cancel_action;
  const interactionAction = action;
  const voiceAction = voice_action;
  const currentRequest = String(current_request || '').trim();
  const isRunning = Boolean(currentRequest);

  const isVoiceEnabled = toBoolean(voice ?? true);
  const isAttachmentEnabled = toBoolean(enable_attachment ?? true);
  const isStopEnabled = toBoolean(stop_enabled ?? (Boolean(stopAction) || isRunning));
  const isDisabled = toBoolean(disabled ?? false);
  const isSubmitDisabled = isDisabled || isRunning;
  const isVoiceDisabled = isSubmitDisabled || voiceTranscribing;
  const areOptionsEditable = toBoolean(options_editable ?? false);
  const isModelEditable = toBoolean(model_editable ?? true);
  const areToolsEditable = toBoolean(tools_editable ?? true);
  const areSkillsEditable = toBoolean(skills_editable ?? true);
  const areMcpEditable = toBoolean(mcp_editable ?? true);
  const shouldShowCapabilities = toBoolean(show_capabilities ?? true);

  const interactionActionWithoutConfirm = React.useMemo(
    () => interactionAction && typeof interactionAction === 'object'
      ? { ...interactionAction, confirm: undefined }
      : interactionAction,
    [interactionAction],
  );

  const buildInteractionPayload = React.useCallback(
    (intent: string, extra: Record<string, any> = {}) => ({
      intent,
      component_id: id,
      value: text,
      model: currentModel,
      selected_tools: selectedToolsState,
      selected_skills: selectedSkillsState,
      selected_mcp: selectedMcpState,
      model_capabilities: capabilityBadges,
        options: optionEntriesForFields(currentOptions, optionFields),
      current_request: currentRequest,
      ...extra,
    }),
    [id, text, currentModel, selectedToolsState, selectedSkillsState, selectedMcpState, capabilityBadges, currentOptions, currentRequest, optionFields],
  );

  const confirmInteraction = React.useCallback(async () => {
    const parsed = parseActionSpec(interactionAction);
    return !parsed.confirm || requestActionConfirm(parsed.confirm);
  }, [interactionAction]);

  const emitInteraction = React.useCallback(
    (intent: string, extra: Record<string, any> = {}) => {
      if (!interactionAction || !onAction) return;
      emitActionSpec(interactionAction, onAction, { [id]: buildInteractionPayload(intent, extra) });
    },
    [id, interactionAction, onAction, buildInteractionPayload],
  );

  const emitPreconfirmedInteraction = React.useCallback(
    (intent: string, extra: Record<string, any> = {}) => {
      if (!interactionActionWithoutConfirm || !onAction) return;
      emitActionSpec(interactionActionWithoutConfirm, onAction, { [id]: buildInteractionPayload(intent, extra) });
    },
    [id, interactionActionWithoutConfirm, onAction, buildInteractionPayload],
  );

  const attachmentPayload = React.useMemo(
    () => attachments.map((f) => ({ name: f.name, size: f.size, type: f.type, url: f.url })),
    [attachments],
  );

  const onSend = async () => {
    if (!text.trim() || !submitAction || !onAction || isSubmitDisabled) return;
    const current = text;
    const parsedSubmitAction = parseActionSpec(submitAction);
    if (parsedSubmitAction.confirm && !(await requestActionConfirm(parsedSubmitAction.confirm))) {
      return;
    }
    const actionWithoutConfirm = submitAction && typeof submitAction === 'object'
      ? { ...submitAction, confirm: undefined }
      : submitAction;
    const moduleName = inferModuleNameFromAction(submitAction);
    const fileAttachments = attachments
      .map((item) => item.file)
      .filter(Boolean) as File[];
    let uploadedAttachments: Array<Record<string, any>> = [];

    if (fileAttachments.length > 0) {
      try {
        const uploaded = await uploadBrowserFiles(fileAttachments, {
          moduleName,
          ingest: ingest !== false,
          actionName: parsedSubmitAction.name,
        });
        uploadedAttachments = [
          ...uploadedAttachments,
          ...uploaded,
        ];
      } catch (uploadError) {
        console.error('[webclient:conversation:composer:upload:error]', uploadError);
        return;
      }
    }

    setText('');
    setInput?.(id, '');
    const composerPayload = {
      intent: 'submit',
      component_id: id,
      text: current,
      attachments: uploadedAttachments,
      options: optionEntriesForFields(currentOptions, optionFields),
      selected_tools: selectedToolsState,
      selected_skills: selectedSkillsState,
      selected_mcp: selectedMcpState,
    };
    emitActionSpec(actionWithoutConfirm, onAction, {
      [id]: composerPayload,
    });
    setAttachments((prev) => {
      prev.forEach((item) => {
        if (item.url.startsWith('blob:')) URL.revokeObjectURL(item.url);
      });
      return [];
    });
  };

  const onStop = () => {
    if (!stopAction || !onAction) return;
    emitActionSpec(stopAction, onAction, { [id]: {
      intent: 'stop',
      component_id: id,
      value: text,
      text,
      current_request: currentRequest,
      model: currentModel,
      selected_tools: selectedToolsState,
      selected_skills: selectedSkillsState,
      selected_mcp: selectedMcpState,
      model_capabilities: capabilityBadges,
      options: optionEntriesForFields(currentOptions, optionFields),
    } });
  };

  const getOptionValue = (name: string) => {
    return currentOptions[name];
  };

  const parseOptionValue = (field: any, rawValue: string) => {
    const type = String(field?.type || '').toLowerCase();
    if (type === 'boolean' || type === 'bool' || type === 'checkbox' || typeof field?.value === 'boolean') {
      return rawValue === 'true';
    }
    if (type === 'integer') return Number.parseInt(rawValue, 10);
    if (type === 'number') return Number(rawValue);
    return rawValue;
  };

  const updateOption = (name: string, rawValue: string, field: any) => {
    setCurrentOptions((prev) => {
      const next = { ...prev };
      if (rawValue === '') {
        delete next[name];
      } else {
        next[name] = parseOptionValue(field, rawValue);
      }
      return next;
    });
  };

  const optionInputType = (field: any) => {
    const type = String(field?.type || '').toLowerCase();
    return type === 'number' || type === 'integer' ? 'number' : 'text';
  };

  const transcribeRecording = React.useCallback(async (file: File) => {
    if (!voiceAction || !onAction) return;
    setVoiceTranscribing(true);
    try {
      const uploaded = await uploadBrowserFile(file, {
        moduleName: inferModuleNameFromAction(voiceAction),
        ingest: false,
        actionName: inferActionName(voiceAction),
      });
      emitActionSpec(voiceAction, onAction, {
        [id]: buildInteractionPayload('voice_transcribe', {
          audio: uploaded,
          target: id,
        }),
      });
    } catch (voiceError) {
      console.error('[reactbootstrap:conversation:composer:voice:error]', voiceError);
    } finally {
      setVoiceTranscribing(false);
    }
  }, [id, voiceAction, onAction, buildInteractionPayload]);

  const startVoiceRecording = async () => {
    try {
      audioRecordingRef.current = await startBrowserAudioRecording('composer-recording');
      setVoiceActive(true);
    } catch (voiceError) {
      console.error('[reactbootstrap:conversation:composer:voice:error]', voiceError);
    }
  };

  const stopVoiceRecording = () => {
    const recording = audioRecordingRef.current;
    if (!recording) return;
    audioRecordingRef.current = null;
    recording
      .stop()
      .then((file) => {
        setVoiceActive(false);
        void transcribeRecording(file);
      })
      .catch((voiceError) => {
        setVoiceActive(false);
        console.error('[reactbootstrap:conversation:composer:voice:error]', voiceError);
      });
  };

  const toggleVoice = async () => {
    if (voiceActive) {
      stopVoiceRecording();
      return;
    }
    if (voiceAction) {
      await startVoiceRecording();
      return;
    }
    if (interactionAction && !(await confirmInteraction())) return;
    const next = !voiceActive;
    setVoiceActive(next);
    emitPreconfirmedInteraction('voice_toggle', { voice_active: next });
  };

  const toggleSelection = (
    valueToToggle: string,
    current: string[],
    setCurrent: React.Dispatch<React.SetStateAction<string[]>>,
    intent: string,
  ) => {
    const has = current.includes(valueToToggle);
    const next = has ? current.filter((v) => v !== valueToToggle) : [...current, valueToToggle];
    setCurrent(next);
    emitInteraction(intent, {
      selected_tools: intent === 'tools_change' ? next : selectedToolsState,
      selected_skills: intent === 'skills_change' ? next : selectedSkillsState,
      selected_mcp: intent === 'mcp_change' ? next : selectedMcpState,
    });
  };

  const onPickModel = (e: React.ChangeEvent<HTMLInputElement>) => {
    const nextModel = e.target.value;
    setCurrentModel(nextModel);
    emitInteraction('model_change', { model: nextModel });
  };

  const onPickFiles = (ev: React.ChangeEvent<HTMLInputElement>) => {
    const files = ev.target.files;
    if (!files?.length) return;
    const picked = Array.from(files).map((file) => ({
      id: `${file.name}_${file.lastModified}_${Math.random().toString(36).slice(2, 8)}`,
      file,
      name: file.name,
      size: file.size,
      type: file.type || 'application/octet-stream',
      url: URL.createObjectURL(file),
    }));
    setAttachments((prev) => [...prev, ...picked]);
    emitPreconfirmedInteraction('attachment_add', {
      attachments: [...attachmentPayload, ...picked.map((f) => ({ name: f.name, size: f.size, type: f.type, url: f.url }))],
    });
    ev.target.value = '';
  };

  const onPaste = (ev: React.ClipboardEvent<HTMLTextAreaElement>) => {
    if (!isAttachmentEnabled || isSubmitDisabled) return;
    const items = ev.clipboardData?.items;
    if (!items?.length) return;
    const images = Array.from(items)
      .filter((item) => item.kind === 'file' && item.type.startsWith('image/'))
      .map((item) => item.getAsFile())
      .filter((file): file is File => Boolean(file))
      .filter((file) => matchesAccept(file, String(attachment_accept || '')));
    if (!images.length) return;
    ev.preventDefault();
    const allowed = toBoolean(attachment_multiple ?? true) ? images : images.slice(0, 1);
    const picked = allowed.map((file) => {
      const namedFile = new File([file], file.name || clipboardImageName(file), {
        type: file.type || 'image/png',
        lastModified: file.lastModified,
      });
      return {
        id: `${namedFile.name}_${namedFile.lastModified}_${Math.random().toString(36).slice(2, 8)}`,
        file: namedFile,
        name: namedFile.name,
        size: namedFile.size,
        type: namedFile.type || 'image/png',
        url: URL.createObjectURL(namedFile),
      };
    });
    setAttachments((prev) => [...prev, ...picked]);
    emitPreconfirmedInteraction('attachment_add', {
      attachments: [
        ...attachmentPayload,
        ...picked.map((f) => ({ name: f.name, size: f.size, type: f.type, url: f.url })),
      ],
    });
  };

  const openFilePicker = async () => {
    if (interactionAction && !(await confirmInteraction())) return;
    fileInputRef.current?.click();
  };

  const removeAttachment = async (fileId: string) => {
    if (interactionAction && !(await confirmInteraction())) return;
    setAttachments((prev) => {
      const target = prev.find((item) => item.id === fileId);
      if (target?.url?.startsWith('blob:')) URL.revokeObjectURL(target.url);
      const next = prev.filter((item) => item.id !== fileId);
      emitPreconfirmedInteraction('attachment_remove', {
        attachments: next.map((f) => ({ name: f.name, size: f.size, type: f.type, url: f.url })),
      });
      return next;
    });
  };

  return (
    <div
      className="composer-container a2ui-composer border d-flex flex-column"
      style={parseStyle(style)}
    >
      {shouldShowCapabilities && !!capabilityBadges.length && (
        <div className="a2ui-composer-capabilities d-flex flex-wrap gap-1">
          {capabilityBadges.map((cap) => (
            <Badge key={`${id}_cap_${cap}`} color="secondary" className="a2ui-composer-chip xsmall">
              {cap}
            </Badge>
          ))}
        </div>
      )}

      {!!attachments.length && (
        <div className="a2ui-composer-attachments d-flex flex-wrap gap-2">
          {attachments.map((file) => (
            <div key={file.id} className="a2ui-composer-attachment d-flex align-items-center gap-2 position-relative">
              <div className="a2ui-composer-attachment-preview d-flex align-items-center justify-content-center overflow-hidden">
                {filePreview(file)}
              </div>
              <div className="flex-grow-1 overflow-hidden">
                <p className="text-truncate xsmall fw-bold m-0">{file.name}</p>
                <p className="xsmall text-muted m-0">{Math.max(1, Math.round(file.size / 1024))} KB</p>
              </div>
              <button
                type="button"
                className="btn btn-xs btn-link p-0 text-danger"
                onClick={() => removeAttachment(file.id)}
              >
                <i className="ri-close-line" />
              </button>
            </div>
          ))}
        </div>
      )}

      <div className="a2ui-composer-input-shell d-flex flex-column">
        <div className="a2ui-composer-input-wrap flex-grow-1">
          <Input
            type="textarea"
            tag="textarea"
            className="a2ui-composer-textarea border-0 shadow-none"
            style={{ minHeight: '68px', maxHeight: '224px', resize: 'none' }}
            placeholder={getLiteral(placeholder) || 'Write a message...'}
            value={text}
            disabled={isSubmitDisabled}
            rows={2}
            onChange={(e: any) => {
              setText(e.target.value);
              setInput?.(id, e.target.value);
            }}
            onPaste={onPaste}
            onInput={(e: any) => {
              const el = e.currentTarget;
              el.style.height = '0px';
              const nextHeight = Math.min(el.scrollHeight, 224);
              el.style.height = `${nextHeight}px`;
              el.style.overflowY = el.scrollHeight > 224 ? 'auto' : 'hidden';
            }}
            onKeyDown={(e: any) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                onSend();
              }
            }}
          />
        </div>

        <div className="a2ui-composer-footer d-flex align-items-center justify-content-between gap-2">
          <div className="a2ui-composer-tools d-flex align-items-center gap-1">
            {isAttachmentEnabled && (
              <>
                <input
                  ref={fileInputRef}
                  type="file"
                  multiple={toBoolean(attachment_multiple ?? true)}
                  accept={String(attachment_accept || '') || undefined}
                  className="d-none"
                  onChange={onPickFiles}
                />
                <Button
                  size="xs"
                  color="link"
                  className="a2ui-composer-tool-btn"
                  title="Attach files"
                  onClick={openFilePicker}
                  disabled={isSubmitDisabled}
                >
                  <i className="ri-attachment-2" />
                </Button>
              </>
            )}

            {isVoiceEnabled && (
              <Button
                size="xs"
                color="link"
                className={cn("a2ui-composer-tool-btn", voiceActive && "is-danger")}
                title={voiceActive ? "Stop recording" : "Record voice"}
                onClick={toggleVoice}
                disabled={isVoiceDisabled}
              >
                <i className={voiceActive ? "ri-mic-off-line" : "ri-mic-line"} />
              </Button>
            )}

            <UncontrolledDropdown>
              <DropdownToggle color="link" size="xs" className="a2ui-composer-tool-btn" disabled={isSubmitDisabled} title="Composer settings">
                <i className="ri-settings-3-line" />
              </DropdownToggle>
              <DropdownMenu className="a2ui-composer-menu shadow">
              {areOptionsEditable && optionFields.length > 0 && (
                <>
                  <DropdownItem header className="xsmall text-muted text-uppercase fw-bold">Options</DropdownItem>
                  <div className="px-3 py-2 border-bottom d-flex flex-column gap-2" style={{ minWidth: '220px' }}>
                    {optionFields.map((field: any) => {
                      const name = String(field.name || '').trim();
                      const label = String(field.label || name);
                      const value = getOptionValue(name);
                      const choices = Array.isArray(field.options) ? field.options : [];
                      const isBoolean = ['boolean', 'bool', 'checkbox'].includes(String(field.type || '').toLowerCase()) || typeof value === 'boolean';
                      return (
                        <label key={`${id}_option_${name}`} className="d-grid align-items-center gap-2 xsmall text-muted" style={{ gridTemplateColumns: 'minmax(88px, 1fr) minmax(96px, 1fr)' }}>
                          <span className="text-truncate font-monospace" title={label}>{label}</span>
                          {(isBoolean || choices.length > 0) ? (
                            <select
                              className="form-select form-select-sm"
                              value={value === undefined || value === null ? '' : String(value)}
                              onChange={(event) => updateOption(name, event.target.value, field)}
                            >
                              {choices.length === 0 && (
                                <>
                                  <option value="true">true</option>
                                  <option value="false">false</option>
                                </>
                              )}
                              {choices.map((choice: any) => {
                                const choiceValue = choice && typeof choice === 'object' ? choice.value : choice;
                                const choiceLabel = choice && typeof choice === 'object' ? choice.label : choice;
                                return <option key={`${name}_${String(choiceValue)}`} value={String(choiceValue)}>{String(choiceLabel)}</option>;
                              })}
                            </select>
                          ) : (
                            <input
                              className="form-control form-control-sm"
                              type={optionInputType(field)}
                              min={field.min}
                              max={field.max}
                              step={field.step}
                              value={value ?? ''}
                              onChange={(event) => updateOption(name, event.target.value, field)}
                            />
                          )}
                        </label>
                      );
                    })}
                  </div>
                </>
              )}
              {isModelEditable && modelOptions.length > 0 && (
                <>
                  <div className="px-3 py-2 border-bottom">
                    <Label className="xsmall text-muted text-uppercase fw-bold mb-1">AI model</Label>
                    <Input 
                      type="select" 
                      tag="select"
                      size="sm" 
                      value={currentModel} 
                      onChange={onPickModel}
                    >
                      {modelOptions.map(m => (
                        <option key={m.id} value={m.id}>{m.name}</option>
                      ))}
                    </Input>
                  </div>
                </>
              )}
              {areToolsEditable && toolOptions.length > 0 && (
                <>
                  <DropdownItem header className="xsmall text-muted text-uppercase fw-bold">Tools</DropdownItem>
                  {toolOptions.map(tool => (
                    <DropdownItem 
                      key={tool.id} 
                      toggle={false}
                      onClick={() => toggleSelection(tool.id, selectedToolsState, setSelectedToolsState, 'tools_change')}
                    >
                      <div className="d-flex align-items-center justify-content-between w-100">
                        <span className="small">{tool.name}</span>
                        {selectedToolsState.includes(tool.id) && <i className="ri-check-line text-primary" />}
                      </div>
                    </DropdownItem>
                  ))}
                </>
              )}
              {areSkillsEditable && skillOptions.length > 0 && (
                <>
                  <DropdownItem divider />
                  <DropdownItem header className="xsmall text-muted text-uppercase fw-bold">Skills</DropdownItem>
                  {skillOptions.map(skill => (
                    <DropdownItem 
                      key={skill.id} 
                      toggle={false}
                      onClick={() => toggleSelection(skill.id, selectedSkillsState, setSelectedSkillsState, 'skills_change')}
                    >
                      <div className="d-flex align-items-center justify-content-between w-100">
                        <span className="small">{skill.name}</span>
                        {selectedSkillsState.includes(skill.id) && <i className="ri-check-line text-primary" />}
                      </div>
                    </DropdownItem>
                  ))}
                </>
              )}
              {areMcpEditable && mcpOptions.length > 0 && (
                <>
                  <DropdownItem divider />
                  <DropdownItem header className="xsmall text-muted text-uppercase fw-bold">MCP</DropdownItem>
                  {mcpOptions.map(mcpItem => (
                    <DropdownItem
                      key={mcpItem.id}
                      toggle={false}
                      onClick={() => toggleSelection(mcpItem.id, selectedMcpState, setSelectedMcpState, 'mcp_change')}
                    >
                      <div className="d-flex align-items-center justify-content-between w-100">
                        <span className="small">{mcpItem.name}</span>
                        {selectedMcpState.includes(mcpItem.id) && <i className="ri-check-line text-primary" />}
                      </div>
                    </DropdownItem>
                  ))}
                </>
              )}
              </DropdownMenu>
            </UncontrolledDropdown>

            {isStopEnabled && stopAction && (
              <Button
                size="xs"
                color="link"
                className="a2ui-composer-tool-btn is-danger"
                onClick={onStop}
                title="Stop generation"
                disabled={!currentRequest}
              >
                <i className="ri-stop-circle-line" />
              </Button>
            )}
          </div>

          {currentModelLabel && (
            <div className="a2ui-composer-model-chip text-truncate" title={currentModelLabel}>
              <i className="ri-cpu-line" />
              <span>{currentModelLabel}</span>
            </div>
          )}

          <Button
            color="primary"
            size="sm"
            className="a2ui-composer-send d-flex align-items-center justify-content-center"
            disabled={!text.trim() || isSubmitDisabled}
            onClick={onSend}
            title="Send"
          >
            <i className="ri-send-plane-2-fill" />
          </Button>
        </div>
      </div>
    </div>
  );
};
