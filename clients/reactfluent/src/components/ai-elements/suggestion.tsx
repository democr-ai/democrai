"use client";

import type { ComponentProps } from "react";
import { cn } from "@/lib/utils";
import { useCallback } from "react";

export const Suggestions = ({
  className,
  children,
  ...props
}: ComponentProps<"div">) => (
  <div className={cn("ds-chat-suggestions", className)} {...props}>
    <div className="ds-chat-suggestions-inner">
      {children}
    </div>
  </div>
);

export type SuggestionProps = Omit<ComponentProps<"button">, "onClick"> & {
  suggestion: string;
  onClick?: (suggestion: string) => void;
};

export const Suggestion = ({
  suggestion,
  onClick,
  className,
  children,
  ...props
}: SuggestionProps) => {
  const handleClick = useCallback(() => {
    onClick?.(suggestion);
  }, [onClick, suggestion]);

  return (
    <button
      className={cn("ds-chat-suggestion", className)}
      onClick={handleClick}
      type="button"
      {...props}
    >
      {children || suggestion}
    </button>
  );
};
