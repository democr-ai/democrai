"use client";

import type { ComponentProps } from "react";
import { Button } from 'design-react-kit';
import { cn } from "@/lib/utils";
import { useCallback } from "react";

export const Suggestions = ({
  className,
  children,
  ...props
}: ComponentProps<"div">) => (
  <div className={cn("w-100 overflow-x-auto pb-2", className)} {...props} style={{ whiteSpace: 'nowrap', msOverflowStyle: 'none', scrollbarWidth: 'none' }}>
    <div className="d-flex flex-nowrap align-items-center gap-2">
      {children}
    </div>
  </div>
);

export type SuggestionProps = Omit<ComponentProps<typeof Button>, "onClick"> & {
  suggestion: string;
  onClick?: (suggestion: string) => void;
};

export const Suggestion = ({
  suggestion,
  onClick,
  className,
  color = "primary",
  outline = true,
  size = "sm",
  children,
  ...props
}: SuggestionProps) => {
  const handleClick = useCallback(() => {
    onClick?.(suggestion);
  }, [onClick, suggestion]);

  return (
    <Button
      className={cn("rounded-pill px-3", className)}
      onClick={handleClick}
      size={size}
      type="button"
      color={color}
      outline={outline}
      {...props}
    >
      {children || suggestion}
    </Button>
  );
};
