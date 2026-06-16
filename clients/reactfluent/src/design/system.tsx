import React from 'react';
import { DefaultButton, PrimaryButton } from '@fluentui/react';

type CommonProps = {
  className?: string;
  children?: React.ReactNode;
  style?: React.CSSProperties;
};

export type ButtonProps = React.ButtonHTMLAttributes<HTMLButtonElement> & CommonProps & {
  color?: string;
  outline?: boolean;
  size?: string;
  appearance?: string;
  icon?: React.ReactNode;
};

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ children, className = '', color, outline, size, type = 'button', icon, appearance: _appearance, ...props }, ref) => {
    const isPrimary = color === 'primary' && !outline;
    const ButtonComponent = isPrimary ? PrimaryButton : DefaultButton;
    const classes = [
      className,
      color ? `ds-button-${String(color).replace(/^outline-/, '')}` : '',
      outline || String(color || '').startsWith('outline-') ? 'ds-button-outline' : '',
      size ? `ds-button-${size}` : '',
    ].filter(Boolean).join(' ');

    return (
      <ButtonComponent
        {...(props as any)}
        componentRef={ref as any}
        type={type}
        className={classes}
      >
        {icon}
        {children}
      </ButtonComponent>
    );
  },
);

Button.displayName = 'Button';

export const ButtonGroup: React.FC<React.HTMLAttributes<HTMLDivElement>> = ({ className = '', ...props }) => (
  <div className={`ds-button-group ${className}`.trim()} role="group" {...props} />
);

export const UncontrolledTooltip: React.FC<{ target?: string; children?: React.ReactNode }> = () => null;

export const Field: React.FC<CommonProps & {
  label?: React.ReactNode;
  validationState?: 'error' | string;
  validationMessage?: React.ReactNode;
}> = ({ label, validationMessage, children, className = '', style }) => (
  <div className={`ds-field ${className}`.trim()} style={style}>
    {label ? <span className="ds-field-label">{label}</span> : null}
    {children}
    {validationMessage ? <span className="ds-field-error">{validationMessage}</span> : null}
  </div>
);

export const Collapse: React.FC<CommonProps & { isOpen?: boolean }> = ({ isOpen, children, className, style }) => {
  if (!isOpen) return null;
  return <div className={className} style={style}>{children}</div>;
};

export const Card: React.FC<React.HTMLAttributes<HTMLDivElement>> = ({ className = '', ...props }) => (
  <div className={`ds-card ${className}`.trim()} {...props} />
);

export const CardBody: React.FC<React.HTMLAttributes<HTMLDivElement>> = ({ className = '', ...props }) => (
  <div className={`ds-card-body ${className}`.trim()} {...props} />
);

export const CardHeader: React.FC<React.HTMLAttributes<HTMLDivElement>> = ({ className = '', ...props }) => (
  <div className={`ds-card-header ${className}`.trim()} {...props} />
);

export const CardTitle: React.FC<React.HTMLAttributes<HTMLHeadingElement>> = ({ className = '', ...props }) => (
  <h3 className={`ds-card-title ${className}`.trim()} {...props} />
);

export const Badge: React.FC<React.HTMLAttributes<HTMLSpanElement> & { color?: string }> = ({
  className = '',
  color = 'secondary',
  ...props
}) => (
  <span className={`ds-badge ds-badge-${color} ${className}`.trim()} {...props} />
);

export type InputProps = React.InputHTMLAttributes<HTMLInputElement> &
  React.TextareaHTMLAttributes<HTMLTextAreaElement> &
  React.SelectHTMLAttributes<HTMLSelectElement> & {
    tag?: 'input' | 'textarea' | 'select' | string;
    contentBefore?: React.ReactNode;
  };

export const Input = React.forwardRef<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement, InputProps>(
  ({ tag, type, className = '', children, contentBefore, ...props }, ref) => {
    const classes = `ds-input ${className}`.trim();
    const control = (() => {
    if (tag === 'textarea' || type === 'textarea') {
      return <textarea ref={ref as any} className={classes} {...(props as any)} />;
    }
    if (tag === 'select' || type === 'select') {
      return <select ref={ref as any} className={classes} {...(props as any)}>{children}</select>;
    }
    return <input ref={ref as any} type={type || 'text'} className={classes} {...(props as any)} />;
    })();
    if (!contentBefore) return control;
    return (
      <span className="ds-input-with-icon">
        <span className="ds-input-icon">{contentBefore}</span>
        {control}
      </span>
    );
  },
);

Input.displayName = 'Input';

export const Select = React.forwardRef<HTMLSelectElement, InputProps>((props, ref) => (
  <Input {...props} ref={ref as any} tag="select" />
));

Select.displayName = 'Select';

export const Option: React.FC<React.OptionHTMLAttributes<HTMLOptionElement> & { text?: string }> = ({
  text,
  children,
  ...props
}) => (
  <option {...props}>{children ?? text}</option>
);

export const Combobox: React.FC<React.SelectHTMLAttributes<HTMLSelectElement> & {
  selectedOptions?: string[];
  onOptionSelect?: (event: React.ChangeEvent<HTMLSelectElement>, data: { optionValue: string }) => void;
}> = ({ selectedOptions, onOptionSelect, onChange, className = '', children, value: _value, ...props }) => (
  <select
    {...props}
    className={`ds-input ds-combobox ${className}`.trim()}
    value={selectedOptions?.[0] || ''}
    onChange={(event) => {
      onChange?.(event);
      onOptionSelect?.(event, { optionValue: event.target.value });
    }}
  >
    {children}
  </select>
);

export const DropdownItem: React.FC<React.ButtonHTMLAttributes<HTMLButtonElement>> = ({ className = '', type = 'button', ...props }) => (
  <button type={type} className={`ds-dropdown-item ${className}`.trim()} {...props} />
);

export const Modal: React.FC<CommonProps & { isOpen?: boolean; toggle?: () => void; centered?: boolean }> = ({
  isOpen,
  children,
  className = '',
}) => {
  if (!isOpen) return null;
  return (
    <div className="ds-modal-backdrop">
      <div className={`ds-modal ${className}`.trim()} role="dialog" aria-modal="true">
        {children}
      </div>
    </div>
  );
};

export const ModalHeader: React.FC<CommonProps & { toggle?: () => void }> = ({ children, toggle, className = '' }) => (
  <div className={`ds-modal-header ${className}`.trim()}>
    <div>{children}</div>
    {toggle ? <Button className="ds-icon-button" onClick={toggle} aria-label="Close"><i className="ri-close-line" /></Button> : null}
  </div>
);

export const ModalBody: React.FC<React.HTMLAttributes<HTMLDivElement>> = ({ className = '', ...props }) => (
  <div className={`ds-modal-body ${className}`.trim()} {...props} />
);

export const ModalFooter: React.FC<React.HTMLAttributes<HTMLDivElement>> = ({ className = '', ...props }) => (
  <div className={`ds-modal-footer ${className}`.trim()} {...props} />
);

export const Offcanvas: React.FC<CommonProps & { isOpen?: boolean; toggle?: () => void; direction?: string }> = ({
  isOpen,
  children,
  className = '',
  style,
}) => {
  if (!isOpen) return null;
  return (
    <aside className={`ds-offcanvas ${className}`.trim()} style={style}>
      {children}
    </aside>
  );
};

export const OffcanvasHeader: React.FC<CommonProps & { toggle?: () => void }> = ({ children, toggle, className = '' }) => (
  <div className={`ds-offcanvas-header ${className}`.trim()}>
    <div>{children}</div>
    {toggle ? <Button className="ds-icon-button" onClick={toggle} aria-label="Close"><i className="ri-close-line" /></Button> : null}
  </div>
);

export const OffcanvasBody: React.FC<React.HTMLAttributes<HTMLDivElement>> = ({ className = '', ...props }) => (
  <div className={`ds-offcanvas-body ${className}`.trim()} {...props} />
);

export const Nav: React.FC<React.HTMLAttributes<HTMLDivElement>> = ({ className = '', ...props }) => (
  <div className={`ds-nav ${className}`.trim()} {...props} />
);

export const NavItem: React.FC<React.HTMLAttributes<HTMLDivElement>> = ({ className = '', ...props }) => (
  <div className={`ds-nav-item ${className}`.trim()} {...props} />
);

export const NavLink: React.FC<React.ButtonHTMLAttributes<HTMLButtonElement>> = ({ className = '', type = 'button', ...props }) => (
  <button type={type} className={`ds-nav-link ${className}`.trim()} {...props} />
);

export const TabContent: React.FC<CommonProps & { activeTab?: string }> = ({ children, className = '', style }) => (
  <div className={`ds-tab-content ${className}`.trim()} style={style}>{children}</div>
);

export const TabPane: React.FC<CommonProps & { tabId?: string }> = ({ children, className = '', style }) => (
  <div className={`ds-tab-pane ${className}`.trim()} style={style}>{children}</div>
);
