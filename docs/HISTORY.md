History
=======

0.14.2 - (2026-05-23)
---------------------
* Standardize certified-diver flows: treat the 3-dives (islands) package as a core split (ask last-dive + nationality before the final summary), matching 2/5/7/9.
* Add the 9-dives / 4 days (islands) package to the islands certified menu and to the pricing menu info (ES/EN).
* Create two island-only services for RAG and quotes: 1-dive / 1 day (islands) and 9-dives / 4 days (islands). Keep 1-dive (islands) out of menus (by-consultation only).
* Add Scuba Diver, Scuba Diver → Open Water, and Open Water with prior PADI e‑learning to the services catalog for RAG (no new buttons to avoid menu noise).
* Normalize USD in JSON to two decimals; in messages display USD as integers (rounded) and COP with thousand separators.
* Unify night-dive notes in summaries: explicitly say when a package includes a night dive; if not, say it doesn’t (ES/EN).
* EN UI: add a checkmark to the “Includes:” label in summaries and service details for visual parity.
* Re-index embeddings to include the new/updated services and pricing.

0.14.1 - (2026-05-22)
---------------------
* Add a "🔙 Volver" button to every step in the Reservar branch (reserva_menu, tours_location, group_type, tours_certified incl. island variant, tours_beginner, beginner_age, courses_menu, courses_open_water_origin, courses_open_water_time, courses_advanced_menu). Clicking it moves the user one step UP in the tree so changing one's mind no longer requires saying "hola" again.
* Split menu keywords: "menu/inicio/start/opciones" still resets to MAIN_MENU; "volver/back/atras/atrás/regresar" now goes one step up (defined per-step via BACK_STEP). Falls back to MAIN_MENU when the current step has no mapping.
* Add MESSAGES entries for courses_open_water_origin / courses_open_water_time / courses_advanced_menu so back-navigation has a prompt to show.
* 12 new conversation tests covering back navigation from each Reservar step plus updates to the two existing 'volver/atrás' tests now asserting one-step-back semantics (suite: 253 tests).

0.14.0 - (2026-05-22)
---------------------
* Restructure top-level menu into two branches: 🤿 Reservar (tours / cursos PADI) and ℹ️ Información (precios / reservas y pago / logística). "Hablar con asesor" remains available via escalation keyword.
* Add `TOURS_LOCATION` step inside the booking branch ("¿Desde dónde harás el tour?") and a `BEGINNER_AGE` qualifier (Bubble Makers vs. 10-year minimum) for the minicourse path.
* Add fuzzy text-to-button matching: typing a button title (e.g. "reservar", "información", "book") triggers the same action as clicking; matching is accent-insensitive so "informacion" maps to "Información". Question words ("cuánto", "how"…) keep their messages on the RAG path.
* Add language-intent detection: "in english", "spanish please", "me lo puedes decir en español?" switch language both at the language step and mid-conversation, acknowledging in the new language and re-showing the main menu.
* Append a back-to-menu hint at the end of pricing / booking / logistics responses so users can navigate to Reservar without re-greeting.
* Add emojis to pricing, booking, and logistics quick-reply buttons.
* Fix duplicate-message bug: incoming text webhooks are now dedupe-checked so Chatwoot's `message_created` + `message_updated` pair for the same id no longer produces double replies.
* New conversations are now auto-toggled to `open` (in addition to being assigned to the owner agent) so they appear in the agent's inbox instead of getting stuck in Pending.
* Fix multiple accent / ñ typos across decision-tree messages (años, niños, acompañantes, mínima, según, multi-día, qué incluye, qué llevar…).
* Update `chatwood-test.html` websiteToken to the active Diving Planet Web inbox token.
* 17 new conversation tests for fuzzy matching, accent-insensitive matching, language switching, and the back-to-menu hint (full suite: 241 tests).

0.13.1 - (2026-05-20)
---------------------
* Refine booking flow: ask certified divers about last dive recency, then Colombian status, then show the service summary.
* Simplify the initial service summary to remove long itinerary/requirements blocks; offer the full itinerary as an optional follow-up.
* Update summary follow-up handling so “yes/no” responses show itinerary or close into free-text Q&A.
* Correct official WhatsApp number across summaries and escalation messages (+57 320 231515).
* Update decision-tree and conversation tests to match the new summary/itinerary behavior.

0.13.0 - (2026-05-19)
---------------------
* Expand knowledge base from owner Q&A (Dudas_V2.pdf): 14 new FAQs and 9 new policies covering food/meals, photos/videos, operating hours, closed days (Dec 25 + Jan 1), Barú ≠ Islas del Rosario clarification, private services, package certification requirements, overnight courses, Divemaster payment structure, DIVE TO HEAL adaptive diving program, and free island pickup.
* Re-index embeddings: updated `load_embeddings.py` to include COP prices from `services.json` and full `pricing.json` indexing; KB grows from 377 → 441 documents.
* Add 80 new conversation tests (207 total): RAG routing for new KB topics, adaptive diving not escalating, and tree response content validation.
* Fix supervisor routing: word-boundary regex for escalation keywords (prevents "persona" false positive), strip trailing punctuation in `_is_substantive_free_text` ("hey?" routes to welcome), and greeting restart (any greeting mid-flow resets to language selection).
* Add DIVE TO HEAL explicit exception to RAG system prompt (ES + EN): disability/accessibility questions answered with program facts, not escalated as medical.
* Add Chatwoot auto-assign: new conversations are assigned to `CHATWOOT_OWNER_AGENT_ID` via API so they appear in the owner's "Mine" view without relying solely on Chatwoot UI auto-assignment.
* Resize Chatwoot test widget (chatwood-test.html) to 680px × 88vh with MutationObserver to survive SDK style resets.

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
