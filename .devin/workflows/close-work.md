---
description: Validate, update history, commit, and push current work
---
# Close work

Use this workflow before handing work to teammates. Keep commits focused and never stage sensitive exports.

1. Read the operating context:

- `docs/project-history/README.md`
- `docs/HISTORY.md`
- `docs/project-history/session-handoff.md`

2. Check branch and pending changes:

```powershell
git status --short --branch
```

3. Inspect changed files and confirm there are no sensitive/raw files staged or unstaged:

```powershell
git diff --stat -- . ':!wasap'
git diff --cached --stat -- . ':!wasap'
git status --short --ignored -- wasap data/knowledge_base
```

Never stage `wasap/`, raw `_chat.txt`, media exports, `.bak`, `pre_dedup`, payment links, IDs, phone numbers, emails, or customer-identifying content unless sanitized.

4. Review conflicts/divergence before pushing:

```powershell
git fetch origin
git status --short --branch
git log --oneline --left-right --cherry-pick HEAD...@{upstream}
```

If the branch is behind or diverged, stop and ask the user how to reconcile before pushing.

5. Run standard validation when code changed:

```powershell
python -m pytest tests/test_chatwoot_buttons.py tests/test_decision_tree.py tests/test_rag_safety.py
python -m compileall src tests
```

If retrieval/vector-store changed, also run:

```powershell
python -m pytest tests/test_retrieval_rerank.py
```

6. Update `docs/HISTORY.md` if the work is a meaningful milestone:

- Add a new version section at the top.
- Use approximate semver.
- Use date `YYYY-MM-DD`.
- Keep bullets short and user-facing.

7. Review and update `docs/project-history/session-handoff.md` before closing:

- Update it if architecture, workflow, risks, validation, current product context, environment details, or next-session priorities changed.
- If no update is needed, explicitly mention in the final report that `session-handoff.md` was reviewed and did not require changes.
- Do not leave important session context only in chat; preserve it in `session-handoff.md` for the next developer/session.

8. Stage only intended files explicitly, for example:

```powershell
git add docs/HISTORY.md docs/project-history/session-handoff.md <changed-files>
```

9. Commit with a concise message:

```powershell
git commit -m "feat: describe the completed milestone"
```

10. Push the current branch:

```powershell
git push origin HEAD
```

11. Finish by reporting:

- Commit hash.
- Remote branch.
- Validation results.
- Any deferred work.
