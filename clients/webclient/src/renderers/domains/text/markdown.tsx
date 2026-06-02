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
      className="w-full max-w-full overflow-x-auto text-sm leading-7 text-foreground/95 [overflow-wrap:anywhere]
        [&>*:first-child]:mt-0 [&>*:last-child]:mb-0
        [&_h1]:mt-6 [&_h1]:mb-2 [&_h1]:text-2xl [&_h1]:font-semibold [&_h1]:text-foreground
        [&_h2]:mt-5 [&_h2]:mb-2 [&_h2]:text-xl [&_h2]:font-semibold [&_h2]:text-foreground
        [&_h3]:mt-4 [&_h3]:mb-2 [&_h3]:text-lg [&_h3]:font-semibold [&_h3]:text-foreground
        [&_p]:my-3
        [&_ul]:my-3 [&_ul]:list-disc [&_ul]:pl-6
        [&_ol]:my-3 [&_ol]:list-decimal [&_ol]:pl-6
        [&_li]:my-1
        [&_a]:text-primary [&_a]:underline [&_a]:underline-offset-4
        [&_blockquote]:my-3 [&_blockquote]:border-l-2 [&_blockquote]:border-border [&_blockquote]:pl-3 [&_blockquote]:italic
        [&_table]:my-4 [&_table]:w-full [&_table]:border-collapse
        [&_th]:border-b [&_th]:border-border [&_th]:px-2 [&_th]:py-1.5 [&_th]:text-left
        [&_td]:border-b [&_td]:border-border/60 [&_td]:px-2 [&_td]:py-1.5
        [&_pre]:my-4 [&_pre]:overflow-x-auto [&_pre]:rounded-md [&_pre]:border [&_pre]:border-border
        [&_pre_code]:block [&_pre_code]:p-3 [&_pre_code]:text-sm"
      style={parsedStyle}
    >
      <Streamdown plugins={streamdownPlugins}>{getLiteral(text)}</Streamdown>
    </div>
  );
};
