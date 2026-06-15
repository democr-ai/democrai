"use client";

import type { ComponentProps } from "react";
import { Collapse } from "design-react-kit";
import { cn } from "@/lib/utils";
import React from "react";

export type SourcesProps = ComponentProps<"div">;

export const Sources = ({ className, children, ...props }: SourcesProps) => {
  const [isOpen, setIsOpen] = React.useState(false);
  
  return (
    <div className={cn("sources-container mb-3 text-primary xsmall", className)} {...props}>
      {React.Children.map(children, child => {
        if (React.isValidElement(child)) {
          return React.cloneElement(child as React.ReactElement<any>, { isOpen, setIsOpen });
        }
        return child;
      })}
    </div>
  );
};

export type SourcesTriggerProps = ComponentProps<"button"> & {
  count: number;
  isOpen?: boolean;
  setIsOpen?: (open: boolean) => void;
};

export const SourcesTrigger = ({
  className,
  count,
  children,
  isOpen,
  setIsOpen,
  ...props
}: SourcesTriggerProps) => (
  <button
    type="button"
    className={cn("btn btn-link btn-xs p-0 d-flex align-items-center gap-2 text-primary fw-bold text-decoration-none", className)}
    onClick={() => setIsOpen?.(!isOpen)}
    {...props}
  >
    {children ?? (
      <>
        <span>Utilizzate {count} fonti</span>
        <i className={cn("ri-arrow-down-s-line fs-5 transition-transform", isOpen && "rotate-180")} />
      </>
    )}
  </button>
);

export type SourcesContentProps = ComponentProps<typeof Collapse> & {
  isOpen?: boolean;
};

export const SourcesContent = ({
  className,
  isOpen,
  ...props
}: SourcesContentProps) => (
  <Collapse
    isOpen={isOpen}
    className={cn("mt-2 d-flex flex-column gap-1", className)}
    {...props}
  />
);

export type SourceProps = ComponentProps<"a">;

export const Source = ({ href, title, children, className, ...props }: SourceProps) => (
  <a
    className={cn("d-flex align-items-center gap-2 text-primary text-decoration-none hover-underline", className)}
    href={href}
    rel="noreferrer"
    target="_blank"
    {...props}
  >
    {children ?? (
      <>
        <i className="ri-book-read-line" />
        <span className="fw-bold">{title}</span>
      </>
    )}
  </a>
);
