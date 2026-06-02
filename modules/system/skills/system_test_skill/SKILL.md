---
name: system_test_skill
title: System Test Skill
description: A simple skill for smoke-testing skill loading.
summary: Echo a short input and use the system test echo tool when useful.
tags:
  - system
  - test
allowed_tools:
  - system.test-echo
  - core.run-skill-script
---

# System Test Skill

Use this skill only for trivial smoke tests.

When the user asks for a minimal system skill test, answer briefly and, if a tool call is useful, call `system.test-echo` with the text to echo.

When the user asks to test a skill script, call `core.run-skill-script` with:

- `skill`: `system.system_test_skill`
- `script`: `echo_summary.py`
- `args`: the short text values to summarize
