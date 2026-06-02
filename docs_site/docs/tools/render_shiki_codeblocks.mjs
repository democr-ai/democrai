import fs from "node:fs/promises";
import path from "node:path";
import process from "node:process";

import { load } from "cheerio";
import { createHighlighter } from "shiki";

const THEMES = {
  light: "github-light-high-contrast",
  dark: "github-dark-high-contrast",
};

const LANGS = [
  "text",
  "bash",
  "shell",
  "sh",
  "python",
  "py",
  "yaml",
  "yml",
  "json",
  "javascript",
  "js",
  "typescript",
  "ts",
  "tsx",
  "html",
  "css",
  "sql",
  "diff",
  "ini",
  "toml",
  "xml",
  "markdown",
  "md",
];

function getLanguage(className) {
  const match = className.match(/language-([A-Za-z0-9_+-]+)/);
  return match ? match[1].toLowerCase() : "text";
}

async function listHtmlFiles(dir) {
  const entries = await fs.readdir(dir, { withFileTypes: true });
  const htmlFiles = [];

  for (const entry of entries) {
    const fullPath = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      htmlFiles.push(...await listHtmlFiles(fullPath));
      continue;
    }
    if (entry.isFile() && fullPath.endsWith(".html")) {
      htmlFiles.push(fullPath);
    }
  }

  return htmlFiles;
}

async function main() {
  const siteDir = process.argv[2];
  if (!siteDir) {
    throw new Error("Missing site directory argument");
  }

  const highlighter = await createHighlighter({
    themes: Object.values(THEMES),
    langs: LANGS,
  });

  const htmlFiles = await listHtmlFiles(siteDir);

  for (const htmlFile of htmlFiles) {
    const source = await fs.readFile(htmlFile, "utf8");
    const $ = load(source, { decodeEntities: false });
    let changed = false;

    $("div.highlight").each((_, element) => {
      const wrapper = $(element);
      const code = wrapper.find("pre > code").first();
      if (!code.length) {
        return;
      }
      if (wrapper.hasClass("highlight--shiki")) {
        return;
      }

      const language = getLanguage(wrapper.attr("class") || "");
      const plainCode = code.text().replace(/\n$/, "");
      const rendered = highlighter.codeToHtml(plainCode, {
        lang: language,
        themes: THEMES,
      });

      wrapper.addClass("codehilite highlight--shiki");
      wrapper.html(rendered);
      changed = true;
    });

    if (changed) {
      await fs.writeFile(htmlFile, $.html(), "utf8");
    }
  }
}

await main();
