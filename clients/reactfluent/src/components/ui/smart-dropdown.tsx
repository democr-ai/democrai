import React from 'react';
import { createPortal } from 'react-dom';
import { createPopper, type Instance, type Placement } from '@popperjs/core';
import { cn } from '@/lib/utils';

type SmartDropdownProps = {
  button: React.ReactNode;
  children: React.ReactNode;
  className?: string;
  menuClassName?: string;
  placement?: Placement;
  fallbackPlacements?: Placement[];
};

export const SmartDropdown: React.FC<SmartDropdownProps> = ({
  button,
  children,
  className,
  menuClassName,
  placement = 'bottom-end',
  fallbackPlacements = ['top-end', 'left-start', 'right-start', 'bottom-start'],
}) => {
  const [open, setOpen] = React.useState(false);
  const toggleRef = React.useRef<HTMLDivElement | null>(null);
  const menuRef = React.useRef<HTMLDivElement | null>(null);
  const popperRef = React.useRef<Instance | null>(null);

  React.useEffect(() => {
    if (!open) return;
    const toggle = toggleRef.current;
    const menu = menuRef.current;
    if (!toggle || !menu) return;

    popperRef.current = createPopper(toggle, menu, {
      placement,
      strategy: 'fixed',
      modifiers: [
        { name: 'offset', options: { offset: [0, 6] } },
        { name: 'preventOverflow', options: { boundary: 'viewport', padding: 8 } },
        { name: 'flip', options: { boundary: 'viewport', padding: 8, fallbackPlacements } },
      ],
    });

    const onPointerDown = (event: MouseEvent | TouchEvent) => {
      const target = event.target as Node | null;
      if (!target) return;
      if (toggleRef.current?.contains(target)) return;
      if (menuRef.current?.contains(target)) return;
      setOpen(false);
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false);
    };

    document.addEventListener('mousedown', onPointerDown, true);
    document.addEventListener('touchstart', onPointerDown, true);
    document.addEventListener('keydown', onKeyDown, true);

    return () => {
      document.removeEventListener('mousedown', onPointerDown, true);
      document.removeEventListener('touchstart', onPointerDown, true);
      document.removeEventListener('keydown', onKeyDown, true);
      popperRef.current?.destroy();
      popperRef.current = null;
    };
  }, [open, placement, fallbackPlacements]);

  React.useEffect(() => {
    if (!open) return;
    popperRef.current?.update();
  }, [open, children]);

  const menu = open && typeof document !== 'undefined'
    ? createPortal(
        <div
          ref={menuRef}
          className={cn('dropdown-menu show smart-dropdown-menu', menuClassName)}
          onClick={() => setOpen(false)}
          role="menu"
        >
          {children}
        </div>,
        document.body,
      )
    : null;

  return (
    <>
      <div ref={toggleRef} className={cn('smart-dropdown d-inline-block', className)}>
        {React.isValidElement(button)
          ? React.cloneElement(button as React.ReactElement<any>, {
              onClick: (event: React.MouseEvent) => {
                event.stopPropagation();
                (button.props as any).onClick?.(event);
                setOpen((value) => !value);
              },
              'aria-expanded': open,
            })
          : (
            <button type="button" className="btn btn-secondary" onClick={() => setOpen((value) => !value)}>
              {button}
            </button>
          )}
      </div>
      {menu}
    </>
  );
};
