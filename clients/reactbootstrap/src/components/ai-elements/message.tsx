"use client";

import type { UIMessage } from "ai";
import type { ComponentProps, HTMLAttributes, ReactElement } from "react";
import { 
  Button, 
  ButtonGroup, 
  UncontrolledTooltip 
} from 'design-react-kit';
import { cn } from "@/lib/utils";
import { cjk } from "@streamdown/cjk";
import { code } from "@streamdown/code";
import { math } from "@streamdown/math";
import { mermaid } from "@streamdown/mermaid";
import React, {
  createContext,
  memo,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import { Streamdown } from "streamdown";

interface MessageContextValue {
  from: UIMessage["role"];
}

const MessageContext = createContext<MessageContextValue | null>(null);

export type MessageProps = HTMLAttributes<HTMLDivElement> & {
  from: UIMessage["role"];
};

export const Message = ({ className, from, children, ...props }: MessageProps) => (
  <MessageContext.Provider value={{ from }}>
    <div
      className={cn(
        "d-flex w-100 flex-column gap-2 mb-3",
        from === "user" ? "align-items-end" : "align-items-start",
        className
      )}
      style={{ maxWidth: '100%' }}
      {...props}
    >
      {children}
    </div>
  </MessageContext.Provider>
);

export const MessageContent = ({
  children,
  className,
  ...props
}: HTMLAttributes<HTMLDivElement>) => {
  const context = useContext(MessageContext);
  const isUser = context?.from === "user";

  return (
    <div
      className={cn(
        "p-3 rounded shadow-sm small border",
        isUser ? "bg-primary text-white border-primary" : "bg-white border-light",
        className
      )}
      style={{ maxWidth: '85%' }}
      {...props}
    >
      {children}
    </div>
  );
};

export const MessageActions = ({
  className,
  children,
  ...props
}: ComponentProps<"div">) => (
  <div className={cn("d-flex align-items-center gap-1 mt-2", className)} {...props}>
    {children}
  </div>
);

export type MessageActionProps = ComponentProps<typeof Button> & {
  tooltip?: string;
  label?: string;
};

export const MessageAction = ({
  tooltip,
  children,
  label,
  color = "link",
  size = "xs",
  className,
  ...props
}: MessageActionProps) => {
  const btnId = React.useId().replace(/:/g, '');
  const context = useContext(MessageContext);
  const isUser = context?.from === "user";

  const button = (
    <Button 
      id={btnId} 
      size={size} 
      type="button" 
      color={color} 
      className={cn("p-1 text-decoration-none", isUser ? "text-white opacity-75 hover-opacity-100" : "text-muted", className)} 
      {...props}
    >
      {children}
      <span className="visually-hidden">{label || tooltip}</span>
    </Button>
  );

  if (tooltip) {
    return (
      <>
        {button}
        <UncontrolledTooltip target={btnId}>{tooltip}</UncontrolledTooltip>
      </>
    );
  }

  return button;
};

interface MessageBranchContextType {
  currentBranch: number;
  totalBranches: number;
  goToPrevious: () => void;
  goToNext: () => void;
  branches: ReactElement[];
  setBranches: (branches: ReactElement[]) => void;
}

const MessageBranchContext = createContext<MessageBranchContextType | null>(null);

const useMessageBranch = () => {
  const context = useContext(MessageBranchContext);
  if (!context) throw new Error("I componenti MessageBranch devono essere usati all'interno di <MessageBranch />");
  return context;
};

export const MessageBranch = ({
  defaultBranch = 0,
  onBranchChange,
  className,
  ...props
}: HTMLAttributes<HTMLDivElement> & { defaultBranch?: number; onBranchChange?: (idx: number) => void }) => {
  const [currentBranch, setCurrentBranch] = useState(defaultBranch);
  const [branches, setBranches] = useState<ReactElement[]>([]);

  const handleBranchChange = useCallback((newBranch: number) => {
    setCurrentBranch(newBranch);
    onBranchChange?.(newBranch);
  }, [onBranchChange]);

  const goToPrevious = useCallback(() => {
    const newBranch = currentBranch > 0 ? currentBranch - 1 : branches.length - 1;
    handleBranchChange(newBranch);
  }, [currentBranch, branches.length, handleBranchChange]);

  const goToNext = useCallback(() => {
    const newBranch = currentBranch < branches.length - 1 ? currentBranch + 1 : 0;
    handleBranchChange(newBranch);
  }, [currentBranch, branches.length, handleBranchChange]);

  const contextValue = useMemo<MessageBranchContextType>(
    () => ({ branches, currentBranch, goToNext, goToPrevious, setBranches, totalBranches: branches.length }),
    [branches, currentBranch, goToNext, goToPrevious]
  );

  return (
    <MessageBranchContext.Provider value={contextValue}>
      <div className={cn("d-grid w-100 gap-2", className)} {...props} />
    </MessageBranchContext.Provider>
  );
};

export const MessageBranchContent = ({
  children,
  ...props
}: HTMLAttributes<HTMLDivElement>) => {
  const { currentBranch, setBranches, branches } = useMessageBranch();
  const childrenArray = useMemo(() => (Array.isArray(children) ? children : [children]), [children]);

  useEffect(() => {
    if (branches.length !== childrenArray.length) setBranches(childrenArray);
  }, [childrenArray, branches, setBranches]);

  return childrenArray.map((branch, index) => (
    <div
      className={cn("d-grid gap-2 overflow-hidden", index === currentBranch ? "d-block" : "d-none")}
      key={branch.key}
      {...props}
    >
      {branch}
    </div>
  ));
};

export const MessageBranchSelector = ({
  className,
  ...props
}: ComponentProps<typeof ButtonGroup>) => {
  const { totalBranches } = useMessageBranch();
  if (totalBranches <= 1) return null;
  return (
    <ButtonGroup className={cn("btn-group-sm mb-2", className)} {...props} />
  );
};

export const MessageBranchPrevious = ({
  children,
  ...props
}: ComponentProps<typeof Button>) => {
  const { goToPrevious, totalBranches } = useMessageBranch();
  return (
    <Button
      aria-label="Ramo precedente"
      disabled={totalBranches <= 1}
      onClick={goToPrevious}
      size="xs"
      color="link"
      className="p-1 text-muted text-decoration-none"
      {...props}
    >
      {children ?? <i className="ri-arrow-left-s-line" />}
    </Button>
  );
};

export const MessageBranchNext = ({
  children,
  ...props
}: ComponentProps<typeof Button>) => {
  const { goToNext, totalBranches } = useMessageBranch();
  return (
    <Button
      aria-label="Ramo successivo"
      disabled={totalBranches <= 1}
      onClick={goToNext}
      size="xs"
      color="link"
      className="p-1 text-muted text-decoration-none"
      {...props}
    >
      {children ?? <i className="ri-arrow-right-s-line" />}
    </Button>
  );
};

export const MessageBranchPage = ({
  className,
  ...props
}: HTMLAttributes<HTMLSpanElement>) => {
  const { currentBranch, totalBranches } = useMessageBranch();
  return (
    <span className={cn("small text-muted align-self-center px-2", className)} {...props}>
      {currentBranch + 1} di {totalBranches}
    </span>
  );
};

const streamdownPlugins = { cjk, code, math, mermaid };

export const MessageResponse = memo(
  ({ className, ...props }: ComponentProps<typeof Streamdown>) => (
    <Streamdown
      className={cn("w-100 markdown-content", className)}
      plugins={streamdownPlugins}
      {...props}
    />
  ),
  (prevProps, nextProps) => prevProps.children === nextProps.children
);

MessageResponse.displayName = "MessageResponse";

export const MessageToolbar = ({
  className,
  children,
  ...props
}: ComponentProps<"div">) => (
  <div
    className={cn("mt-2 d-flex w-100 align-items-center justify-content-between gap-3", className)}
    {...props}
  >
    {children}
  </div>
);
