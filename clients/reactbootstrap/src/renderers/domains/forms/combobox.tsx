import React from 'react';
import { parseStyle } from '@/utils/style';
import { emitActionSpec, getLiteral, normalizeOptions, requestActionConfirm } from '@/renderers/shared';
import { 
  Input,
  FormGroup,
  Label
} from 'design-react-kit';
import { UncontrolledDropdown, DropdownItem, DropdownToggle, DropdownMenu } from 'reactstrap';
import { cn } from '@/lib/utils';

export const Combobox: React.FC<any> = ({
  id,
  label,
  options = [],
  value,
  placeholder,
  action,
  onAction,
  setInput,
  style,
  syncInitialInput = true,
}) => {
  const normalized = React.useMemo(() => normalizeOptions(options), [options]);
  const [open, setOpen] = React.useState(false);
  const [query, setQuery] = React.useState('');
  const [selected, setSelected] = React.useState(value == null ? '' : String(value));

  React.useEffect(() => {
    const next = value == null ? '' : String(value);
    setSelected(next);
    if (syncInitialInput) setInput?.(id, next);
  }, [id, setInput, syncInitialInput, value]);

  const selectedLabel = normalized.find((entry) => String(entry.value) === selected)?.label || '';
  const filtered = normalized.filter((entry) => entry.label.toLowerCase().includes(query.trim().toLowerCase()));

  const toggle = () => setOpen(!open);

  return (
    <FormGroup style={parseStyle(style)}>
      {label && <Label for={id}>{getLiteral(label)}</Label>}
      <UncontrolledDropdown isOpen={open} toggle={toggle} className="w-100">
        <DropdownToggle
          tag="button"
          className="btn btn-outline-secondary w-100 d-flex justify-content-between align-items-center"
          id={id}
        >
          <span className="text-truncate">{selectedLabel || getLiteral(placeholder || 'Cerca...')}</span>
          <i className="ri-arrow-down-s-line" />
        </DropdownToggle>
        <DropdownMenu className="w-100 shadow">
          <div className="p-2 border-bottom">
            <Input
              autoFocus
              className="form-control-sm"
              placeholder="Cerca..."
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onClick={(e) => e.stopPropagation()}
            />
          </div>
          <div style={{ maxHeight: '240px', overflowY: 'auto' }}>
            {filtered.length > 0 ? filtered.map((entry, index) => {
              const isSelected = String(entry.value) === selected;
              return (
                <DropdownItem
                  key={`${id}_combo_${index}`}
                  active={isSelected}
                  onClick={async () => {
                    const next = String(entry.value);
                    if (next === selected) {
                      setOpen(false);
                      return;
                    }
                    if (action?.confirm && !(await requestActionConfirm(action.confirm))) {
                      setOpen(false);
                      return;
                    }
                    setSelected(next);
                    setInput?.(id, next);
                    const actionWithoutConfirm = action && typeof action === 'object'
                      ? { ...action, confirm: undefined }
                      : action;
                    emitActionSpec(actionWithoutConfirm, onAction, { [id]: next, value: next });
                    setOpen(false);
                  }}
                >
                  <div className="d-flex align-items-center justify-content-between w-100">
                    <span className="small">{entry.label}</span>
                    {isSelected && <i className="ri-check-line" />}
                  </div>
                </DropdownItem>
              );
            }) : (
              <div className="p-2 text-center text-muted small">Nessun risultato</div>
            )}
          </div>
        </DropdownMenu>
      </UncontrolledDropdown>
    </FormGroup>
  );
};
