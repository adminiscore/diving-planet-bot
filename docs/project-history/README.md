# Project history

This folder contains the operating context needed to resume work on the Diving Planet Bot without losing traceability.

## How to use

- Read `docs/HISTORY.md` for a quick version-by-version overview of what has been built.
- Read `docs/project-history/session-handoff.md` before changing code; it contains the current architecture, branch context, validation commands, risks, and privacy rules.
- Use `/start-context` at the start of a session and `/close-work` before committing/pushing work.

## Privacy rule

Raw customer exports, WhatsApp conversations, voice notes, contact cards, photos, PDFs, payment links, IDs, and backup dumps must not be committed. Only curated, sanitized knowledge-base content should be versioned.
