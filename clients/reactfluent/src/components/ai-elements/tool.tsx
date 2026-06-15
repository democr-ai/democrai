"use client";

import type { DynamicToolUIPart, ToolUIPart } from "ai";
import React, { type ComponentProps, type ReactNode } from "react";
import {
  Badge,
  Button,
  Card,
  CardBody,
  Collapse,
} from '@/design/system';
import { cn } from "@/lib/utils";
import { isValidElement } from "react";
import { CodeBlock } from "./code-block";

export type ToolPart = ToolUIPart | DynamicToolUIPart;

const statusLabels: Record<ToolPart["state"], string> = {
  "approval-requested": "Awaiting approval",
  "approval-responded": "Responded",
  "input-available": "Running",
  "input-streaming": "Waiting",
  "output-available": "Completed",
  "output-denied": "Denied",
  "output-error": "Error",
};

const statusIcons: Record<ToolPart["state"], ReactNode> = {
  "approval-requested": <i className="ri-time-line me-1" />,
  "approval-responded": <i className="ri-checkbox-circle-line me-1" />,
  "input-available": <i className="ri-loader-4-line ri-spin me-1" />,
  "input-streaming": <i className="ri-checkbox-blank-circle-line me-1" />,
  "output-available": <i className="ri-checkbox-circle-fill text-success me-1" />,
  "output-denied": <i className="ri-close-circle-fill text-danger me-1" />,
  "output-error": <i className="ri-error-warning-fill text-danger me-1" />,
};

export const getStatusBadge = (status: ToolPart["state"]) => {
  let color = "secondary";
  if (status === "output-available") color = "success";
  if (status === "output-denied" || status === "output-error") color = "danger";
  
  return (
    <Badge color={color} className="d-inline-flex align-items-center rounded-pill xsmall">
      {statusIcons[status]}
      {statusLabels[status]}
    </Badge>
  );
};

export const Tool = ({ className, children, ...props }: ComponentProps<"div">) => {
  const [isOpen, setIsOpen] = React.useState(false);
  
  return (
    <Card className={cn("mb-3 shadow-none border", className)} {...props}>
      <div className="tool-context-provider" data-is-open={isOpen}>
        {React.Children.map(children, child => {
          if (isValidElement(child)) {
            return React.cloneElement(child as any, { isOpen, toggle: () => setIsOpen(!isOpen) });
          }
          return child;
        })}
      </div>
    </Card>
  );
};

export const ToolHeader = ({
  className,
  title,
  type,
  state,
  toolName,
  isOpen,
  toggle,
  ...props
}: any) => {
  const derivedName = type === "dynamic-tool" ? toolName : type.split("-").slice(1).join("-");

  return (
    <div
      className={cn("d-flex w-100 align-items-center justify-content-between p-2 cursor-pointer", className)}
      onClick={toggle}
      style={{ cursor: 'pointer' }}
      {...props}
    >
      <div className="d-flex align-items-center gap-2">
        <i className="ri-tools-fill text-muted" />
        <span className="fw-bold small">{title ?? derivedName}</span>
        {getStatusBadge(state)}
      </div>
      <i className={cn("ri-arrow-down-s-line text-muted transition-transform", isOpen && "ri-rotate-180")} />
    </div>
  );
};

export const ToolContent = ({ className, isOpen, children, ...props }: any) => (
  <Collapse isOpen={isOpen}>
    <CardBody className={cn("p-3 pt-0 d-grid gap-3", className)} {...props}>
      {children}
    </CardBody>
  </Collapse>
);

export const ToolInput = ({ className, input, ...props }: any) => (
  <div className={cn("d-grid gap-1 overflow-hidden", className)} {...props}>
    <h6 className="text-muted xsmall text-uppercase fw-bold m-0">Parameters</h6>
    <div className="rounded bg-light p-2 border">
      <CodeBlock code={JSON.stringify(input, null, 2)} language="json" />
    </div>
  </div>
);

export const ToolOutput = ({
  className,
  output,
  errorText,
  ...props
}: any) => {
  if (!(output || errorText)) return null;

  let Output = <div>{output as ReactNode}</div>;

  if (typeof output === "object" && !isValidElement(output)) {
    Output = <CodeBlock code={JSON.stringify(output, null, 2)} language="json" />;
  } else if (typeof output === "string") {
    Output = <CodeBlock code={output} language="json" />;
  }

  return (
    <div className={cn("d-grid gap-1", className)} {...props}>
      <h6 className="text-muted xsmall text-uppercase fw-bold m-0">{errorText ? "Error" : "Result"}</h6>
      <div className={cn("overflow-auto rounded p-2 border xsmall", errorText ? "bg-danger-subtle text-danger" : "bg-light")}>
        {errorText && <div>{errorText}</div>}
        {Output}
      </div>
    </div>
  );
};
