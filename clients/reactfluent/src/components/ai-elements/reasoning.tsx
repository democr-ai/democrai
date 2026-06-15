"use client";

import type { ComponentProps, ReactNode } from "react";
import { Collapse } from "@/design/system";
import { cn } from "@/lib/utils";
import { cjk } from "@streamdown/cjk";
import { code } from "@streamdown/code";
import { math } from "@streamdown/math";
import { mermaid } from "@streamdown/mermaid";
import {
  createContext,
  memo,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { Streamdown } from "streamdown";
import { Shimmer } from "./shimmer";

interface ReasoningContextValue {
  isStreaming: boolean;
  isOpen: boolean;
  setIsOpen: (open: boolean) => void;
  duration: number | undefined;
}

const ReasoningContext = createContext<ReasoningContextValue | null>(null);

export const useReasoning = () => {
  const context = useContext(ReasoningContext);
  if (!context) {
    throw new Error("I componenti Reasoning devono essere usati all'interno di <Reasoning />");
  }
  return context;
};

export type ReasoningProps = ComponentProps<"div"> & {
  isStreaming?: boolean;
  open?: boolean;
  defaultOpen?: boolean;
  onOpenChange?: (open: boolean) => void;
  duration?: number;
};

const AUTO_CLOSE_DELAY = 1000;
const MS_IN_S = 1000;

export const Reasoning = memo(
  ({
    className,
    isStreaming = false,
    open,
    defaultOpen,
    onOpenChange,
    duration: durationProp,
    children,
    ...props
  }: ReasoningProps) => {
    const resolvedDefaultOpen = defaultOpen ?? isStreaming;
    const [isOpen, setIsOpen] = useState(resolvedDefaultOpen);
    const [duration, setDuration] = useState<number | undefined>(durationProp);

    const hasEverStreamedRef = useRef(isStreaming);
    const [hasAutoClosed, setHasAutoClosed] = useState(false);
    const startTimeRef = useRef<number | null>(null);

    useEffect(() => {
      if (isStreaming) {
        hasEverStreamedRef.current = true;
        if (startTimeRef.current === null) {
          startTimeRef.current = Date.now();
        }
      } else if (startTimeRef.current !== null) {
        setDuration(Math.ceil((Date.now() - startTimeRef.current) / MS_IN_S));
        startTimeRef.current = null;
      }
    }, [isStreaming]);

    useEffect(() => {
      if (isStreaming && !isOpen && defaultOpen !== false) {
        setIsOpen(true);
        onOpenChange?.(true);
      }
    }, [isStreaming, isOpen, defaultOpen, onOpenChange]);

    useEffect(() => {
      if (hasEverStreamedRef.current && !isStreaming && isOpen && !hasAutoClosed) {
        const timer = setTimeout(() => {
          setIsOpen(false);
          setHasAutoClosed(true);
          onOpenChange?.(false);
        }, AUTO_CLOSE_DELAY);
        return () => clearTimeout(timer);
      }
    }, [isStreaming, isOpen, hasAutoClosed, onOpenChange]);

    const contextValue = useMemo(
      () => ({ duration, isOpen, isStreaming, setIsOpen }),
      [duration, isOpen, isStreaming]
    );

    return (
      <ReasoningContext.Provider value={contextValue}>
        <div className={cn("reasoning-container mb-3", className)} {...props}>
          {children}
        </div>
      </ReasoningContext.Provider>
    );
  }
);

export type ReasoningTriggerProps = ComponentProps<"button"> & {
  getThinkingMessage?: (isStreaming: boolean, duration?: number) => ReactNode;
};

const defaultGetThinkingMessage = (isStreaming: boolean, duration?: number) => {
  if (isStreaming || duration === 0) {
    return <Shimmer duration={1}>Ragionamento in corso...</Shimmer>;
  }
  if (duration === undefined) {
    return <span>Assistant Reasoning</span>;
  }
  return <span>Ha pensato per {duration} secondi</span>;
};

export const ReasoningTrigger = memo(
  ({
    className,
    children,
    getThinkingMessage = defaultGetThinkingMessage,
    ...props
  }: ReasoningTriggerProps) => {
    const { isStreaming, isOpen, duration, setIsOpen } = useReasoning();

    return (
      <button
        type="button"
        className={cn(
          "btn btn-link btn-xs p-0 d-flex align-items-center gap-2 text-muted fw-bold text-decoration-none",
          className
        )}
        onClick={() => setIsOpen(!isOpen)}
        {...props}
      >
        {children ?? (
          <>
            <i className="ri-brain-line fs-5" />
            {getThinkingMessage(isStreaming, duration)}
            <i
              className={cn(
                "ri-arrow-down-s-line fs-5 transition-transform",
                isOpen && "rotate-180"
              )}
            />
          </>
        )}
      </button>
    );
  }
);

export type ReasoningContentProps = ComponentProps<typeof Collapse> & {
  children: string;
};

const streamdownPlugins = { cjk, code, math, mermaid };

export const ReasoningContent = memo(
  ({ className, children, ...props }: ReasoningContentProps) => {
    const { isOpen } = useReasoning();
    return (
      <Collapse isOpen={isOpen} className={cn("mt-2", className)} {...props}>
        <div className="p-3 border rounded bg-light text-muted xsmall">
          <Streamdown plugins={streamdownPlugins}>
            {children}
          </Streamdown>
        </div>
      </Collapse>
    );
  }
);

Reasoning.displayName = "Reasoning";
ReasoningTrigger.displayName = "ReasoningTrigger";
ReasoningContent.displayName = "ReasoningContent";
