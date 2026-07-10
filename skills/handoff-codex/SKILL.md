---
name: handoff-codex
description: Write a concise handoff document for an overloaded Codex App session. Use when a Handoff Codex hook says a deferred handoff is pending, or when the user asks to create a handoff, resume in a new thread, reduce context, avoid compaction, or preserve current state before continuing elsewhere.
---

# Handoff Codex

Write a small handoff document so a fresh Codex App thread can continue with clean context.

This skill is normally triggered after the plugin lets the current response finish, then injects a deferred handoff instruction on the next user prompt.

## Workflow

1. Use the hook-provided handoff directory if the latest context includes one. Otherwise use `work/handoffs/<project-name>/`.
2. Read only the minimum state needed:
   - `CONTEXT.md` if present.
   - Existing task plan/progress files only if current context points to them.
   - `git status --short` when inside a git repo.
3. Create `handoff-<YYYYMMDD-HHMM>.md` in the handoff directory.
4. Keep it concise. Link or name files; do not paste long logs or large code.
5. Stop after giving the resume prompt. Do not continue the original task unless the user explicitly asks.

## Handoff Template

```md
# Handoff: <project-name>

## Goal / Current Focus
<one short paragraph>

## State
- Done: ...
- In progress: ...
- Next: ...

## Decisions / Constraints
- ...

## Open Questions / Blockers
- ...

## Pointers
- ...

## Resume Prompt
Use $handoff-codex to resume from `<absolute path to this handoff>`.
Continue from the "Next" item first, preserve the listed constraints, and verify before claiming completion.
```

## Rules

- Redact secrets, tokens, passwords, cookies, private keys, and sensitive personal data.
- If invoked from a hook, treat the hook as the source of the handoff directory and token threshold.
- Do not edit `~/.codex/config.toml`, `~/.codex/hooks.json`, or plugin files while creating a handoff.
- Do not run a new Codex session yourself. Tell the user what to paste in a new Codex App thread.
- If resuming from an existing handoff, read that handoff and continue from its `Next` item.

## Final Response Shape

```md
交接文档已生成：`<absolute path>`

新开一个 Codex App 线程后发送：

Use $handoff-codex to resume from `<absolute path>`.
```
