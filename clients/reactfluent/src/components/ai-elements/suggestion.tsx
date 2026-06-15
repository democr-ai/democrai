"use client";

import type { ComponentProps } from "react";
import { cn } from "@/lib/utils";
import { useCallback } from "react";

export const Suggestions = ({
  className,
  children,
  ...props
}: ComponentProps<"div">) => (
  <div className={cn("a2ui-chat-suggestions", className)} {...props}>
    <div className="a2ui-chat-suggestions-inner">
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
      className={cn("a2ui-chat-suggestion", className)}
      onClick={handleClick}
      type="button"
      {...props}
    >
      {children || suggestion}
    </button>
  );
};
