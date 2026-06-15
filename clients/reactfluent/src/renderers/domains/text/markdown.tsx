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
      className="a2ui-markdown markdown-content w-100 overflow-auto"
      style={parsedStyle}
    >
      <Streamdown plugins={streamdownPlugins}>{getLiteral(text)}</Streamdown>
    </div>
  );
};
