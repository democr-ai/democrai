# Skills

Skills are reusable instruction packages loaded by agents and AI orchestration.
They live under:

```text
modules/<module>/skills/<skill_name>/
  SKILL.md
  assets/
  scripts/
```

Only `SKILL.md` is required. `assets/` and `scripts/` are optional and are
discovered relative to the skill folder.

## What Belongs In A Skill

Use a skill for:

- domain-specific instructions;
- tool usage guidance;
- examples and constraints;
- output expectations;
- short operational policies for an agent.

Do not put business persistence, database access, or platform calls in a skill.
Those belong in actions and tools. A skill tells the model how to behave; it is
not the implementation of the feature.

## Basic Skill Document

Create `modules/<module>/skills/report_context/SKILL.md`:

```markdown
---
name: report_context
title: Report Context
description: Guidance for answering questions about reports.
summary: Use report tools to inspect report state before answering.
tags:
  - reports
  - documents
allowed_tools:
  - reports.get-report
  - reports.search-reports
---

# Report Context

Use this skill when answering questions about reports.

First inspect the report state with `reports.get-report` when the user asks
about a specific report.

Use `reports.search-reports` when the user asks for information that may be
spread across several reports.

If the tool result is incomplete, say what is missing instead of inventing
report content.
```

The module loader registers the skill as `reports.report_context` for module
`reports`.

## Front Matter Fields

The skill loader reads these front matter fields:

| Field | Purpose |
| --- | --- |
| `name` | Stable skill name. Module skills are qualified with the module name. |
| `title` | Human-readable label. |
| `description` | Short discovery description. |
| `summary` | Compact model-facing summary. |
| `tags` | Discovery tags. |
| `input_hint` | Optional hint about expected input. |
| `usage` | Optional usage notes. |
| `examples` | Example prompts or situations. |
| `constraints` | Rules the model should follow. |
| `outputs` | Expected output forms. |
| `version` | Skill version. |
| `author` | Skill author metadata. |
| `homepage` | Related documentation URL. |
| `allowed_tools` | Tools the skill expects or allows. |
| `access` | Access policy rules for skill-owned scripts or external resources. |

Unknown front matter keys are preserved as metadata, but new module behavior
should use the documented fields above.

## Body Guidelines

The body should be explicit and operational:

```markdown
# Report Context

When the user asks about a specific report:

1. Use `reports.get-report`.
2. Read the returned status and summary.
3. Answer only from the tool result.

When the user asks a broad question:

1. Use `reports.search-reports`.
2. Compare the returned matches.
3. Mention if more retrieval would be needed.
```

Good skill text gives the agent a sequence of decisions. Avoid vague advice
such as "be helpful" or "use tools when useful".

## Allowed Tools

Use `allowed_tools` to document the tool surface the skill expects:

```yaml
allowed_tools:
  - reports.get-report
  - reports.search-reports
```

This is part of the skill contract. Keep it aligned with the tools declared by
agents that load the skill.

## Assets And Scripts

If the skill folder contains files under `assets/` or `scripts/`, the loader
records their relative paths:

```text
modules/reports/skills/report_context/
  SKILL.md
  assets/
    glossary.md
  scripts/
    normalize_report.py
```

Use assets for static context files and scripts only when the runtime explicitly
supports executing the skill script through an approved tool. Do not rely on a
skill script as hidden module business logic.

## Loading Skills From Agents

Agents reference skills by name:

```python
@agent(
    "report-agent",
    tools=["reports.get-report", "reports.search-reports"],
    skills=["reports.report_context"],
    objective="chat",
)
async def report_agent(...):
    ...
```

Module code can also inspect skills through the SDK:

```python
skills = module_sdk.ai.list_skills(module_name="reports")
```

## Skill Design Checklist

Before adding a skill, check:

- the skill has one clear purpose;
- the tool list is explicit;
- the body tells the model when to use each tool;
- constraints are written as concrete rules;
- implementation logic remains in actions/tools;
- any scripts or assets are optional supporting material, not hidden runtime
  dependencies.
