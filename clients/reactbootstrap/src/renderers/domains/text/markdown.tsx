import React from "react";
import { cjk } from "@streamdown/cjk";
import { code } from "@streamdown/code";
import { math } from "@streamdown/math";
import { mermaid } from "@streamdown/mermaid";
import { Streamdown } from "streamdown";
import "streamdown/styles.css";
import { parseStyle } from "@/utils/style";
import { getLiteral } from "@/renderers/shared";

const streamdownPlugins = { cjk, code, math, mermaid };

export const Markdown: React.FC<any> = ({ text, style }) => {
  const parsedStyle = parseStyle(style);

  return (
    <div
      className="w-100 overflow-auto markdown-body small"
      style={parsedStyle}
    >
      <Streamdown plugins={streamdownPlugins}>{getLiteral(text)}</Streamdown>
    </div>
  );
};
