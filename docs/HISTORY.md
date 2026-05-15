History
=======

0.12.0 - (2026-05-15)
---------------------
* Implement real Chatwoot human handoff by toggling escalated conversations to `pending` after sending the internal lead note.
* Add Chatwoot regression coverage for handoff delivery and failed-handoff retry preservation.
* Harden decision-tree language detection to avoid false English positives from Spanish inputs such as `en español`.

0.11.0 - (2026-05-13)
---------------------
* Add automatic lead-summary private notes in Chatwoot on escalation (keyword, sensitive, and tree-triggered).
* Rewrite RAG system prompt with brand_tone.json: WhatsApp style, explicit prohibitions, escalation criteria.
* Fix snorkeling bug: group_type choice 4 from islands now maps to the correct island variant.
* Add exhaustive conversation test dataset (127 tests, 18 blocks covering all tree paths, escalation, RAG, PII, English flows, lead summaries, and quick replies).
* Add /runtests Claude Code skill with block-level keyword filtering.
* Fix dev environment: Chatwoot webhook was pointing to port 8001 instead of 8000; add message_updated event subscription so button clicks reach the bot.
* Replace Windows-incompatible country flag emojis (🇨🇴/🇺🇸) with universally supported globe emojis (🌎/🌐).

0.10.0 - (2026-05-13)
---------------------
* Align the decision tree with `services.json` as the service source of truth.
* Add guided coverage for island service variants and PADI specialties.
* Expand curated FAQs with beginner diving knowledge, safety guidance, equipment basics, course comparisons, and marine-life guidance.
* Update visual tree docs, MVP KB audit, and decision-tree tests.

0.9.0 - (2026-05-12)
--------------------
* Define MVP direction around informing, qualifying, recommending, and preparing human-assisted conversion.
* Add intent matrix and knowledge-base audit to keep tree, RAG, and human handoff responsibilities clear.
* Add a simple infrastructure diagram and strengthen session close workflow traceability.

0.8.0 - (2026-05-11)
--------------------
* Improve Cartagena decision-tree branches for beginners, snorkeling, private services, and certified multi-day packages.
* Add safety/privacy tests and remove raw WhatsApp exports/backups from Git tracking.

0.7.0 - (2026-05-10)
--------------------
* Upgrade the certified-diver `2 dives / 1 day` branch with clearer flow logic and Spanish documentation.
* Expand decision-tree coverage for certified divers, courses, pricing, bookings, logistics, and escalation paths.

0.6.0 - (2026-05-08)
--------------------
* Implement real Chatwoot `input_select` buttons for decision-tree menus.
* Add numeric/text fallback parsing plus polling and deduplication for local Chatwoot button clicks and missed messages.

0.5.0 - (2026-05-07)
--------------------
* Add multi-environment infrastructure for dev, pre, and pro deployments.
* Add bot Dockerfile, VPS compose/Caddy setup, `.env.*.example` templates, and environment loading support.

0.4.0 - (2026-05-07)
--------------------
* Expand curated knowledge base with pricing, availability, discounts, escalation, and sanitized real conversation examples.
* Update embeddings loader and retrieval data preparation.

0.3.0 - (2026-04-10)
--------------------
* Implement Phase 2 RAG agent and supervisor routing.
* Route conversations between deterministic decision tree, retrieval answers, and human escalation.

0.2.0 - (2026-04-10)
--------------------
* Implement Phase 1 deterministic decision tree with Chatwoot integration.
* Add initial booking flow, service routing, webhook handling, and automated replies.

0.1.0 - (2026-04-10)
--------------------
* Create initial Diving Planet Bot repository baseline.
