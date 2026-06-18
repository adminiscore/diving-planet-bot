---
description: Load project context before starting a session
---
# Start context

Use this workflow at the beginning of a work session to understand the repo before editing anything.

1. Read `docs/project-history/README.md`.
2. Read `docs/HISTORY.md`.
3. Read `docs/project-history/session-handoff.md`.
4. Check the current Git state:

```powershell
git status --short --branch
```

5. Review the latest commits:

```powershell
git log --oneline -8
```

6. Summarize for the user:

- Current branch and sync state.
- Latest version/history milestone.
- Relevant architecture context.
- Sensitive-data rule reminder.
- Recommended next step.

7. Do not edit code or docs unless the user explicitly asks for implementation.
