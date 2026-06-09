History
=======

0.16.0 - (2026-06-05)
---------------------
* Mixed cart: kids age question now fires INLINE when adding Minicurso (not at end of checkout), supports `<8` / `8-10` / `10+` / `Varios rangos`, and re-prompts on modify; delete-then-re-add starts fresh.
* Mixed cart: new `📍 Cambiar origen` action in `mixed_cart_actions` re-asks Cartagena vs. Islas and remaps prices and cert/course plan variants on the fly via `_remap_cart_for_location`.
* Mixed final summary splits the Minicurso row into adult minicurso + kids snorkel + Bubble Makers sub-rows with correct per-range pricing; `kids_under_8_count` and `kids_eight_to_ten_count` drive lead-note breakdown.
* Large-group `6+` exact-count UX for kids quantity (mirrors `MIXED_ADD_QTY` pattern via `mixed_pending_exact` flag).
* Back-routing: Volver from `MIXED_CART_LOCATION`, `MIXED_CART_MODIFY_PICK`, `MIXED_CART_REMOVE_PICK`, `MIXED_FINAL_KIDS_U8`, `MIXED_FINAL_KIDS_810` now routes through each handler so `cart_lines` is shown (both literal-keyword and LLM-intent back paths in supervisor).
* Branch reset: `feature/dev_alvaro` was rebased onto `feature/pruebaGon`'s tip (e1ee6b6) by replaying the full working tree as a single port commit, so Gonzalo and Gadea can fast-forward without conflicts. Backup retained at `backup/dev_alvaro_pre_pruebaGon_rebase_2026-06-05`.

0.15.3 - (2026-06-04)
---------------------
* Restore the certified-diving booking flow in the mixed cart to a two-step menu: `2 dives / 1 day` first, then a dedicated `multi-day package (3 or more dives)` submenu.
* Bring back all certified multi-day packages from `services.json` inside booking, including Cartagena `3/4/5/7/9 dives` and the island-only `4 dives` night-dive variant.
* Keep the exact certified service ID through cart preview, refresher/split handling, final summary, and lead-note generation so mixed-group bookings preserve the chosen package.
* Add regression coverage for the restored menus, island variants, and mixed-cart certified package handling.

0.15.2 - (2026-06-03)
---------------------
* Refresher no longer converts certified `2 dives / 1 day` into a minicourse: `2_dives_1_day` (and its island variant) added to `REFRESHER_PRESERVE_SERVICES`, so the service stays as buceo certificado and the refresher is annotated.
* Companion-from-single + cart flow now asks "¿Cuántas de las N personas quieren hacer el *refresher*?" when there are 2+ certified divers, and persists `refresher_qty` into the mixed cart on entry so it shows in the final summary.
* Speaker's own refresher (from the initial 2_dives_1_day flow) is now carried into the mixed cart when joining companions, so the cart counts both speaker + companions who confirmed refresher.
* Cart cleanup: `refresh` items are skipped from the paid rows of `RESERVA DIVING PLANET` and rendered as a free `🧑‍🏫 Refresher incluido: N personas — sin coste adicional` line in the EXTRAS block. Cart label changed from "Minicurso / Refresher" to "Refresher (sin coste)".
* Companion intent detection covers digit/word-noun concatenations (`3amigos`, `sieteamigos`, `4hijos`) via a normalization pass that splits them before regex matching.
* Mixed-group info cards are now compact when there are 2+ allocations (drops includes/not_included/link blocks), separated by a horizontal rule. Single-allocation cards keep the full detail.
* Itinerary view now shows the activity title at the top.
* Cert question text (`¿Son buzos certificados?`) trimmed to remove the numbered list duplicated by the quick replies; "Anotado" confirmation prefixed with `✅` and clarified.
* Local dev page `chatwood-test.html` is gitignored (contains personal Chatwoot tokens) and got SDK retry + status indicator so the chat button no longer fails silently when Docker is still starting.

0.15.1 - (2026-06-02)
---------------------
* Harden meal / dietary RAG answers so food questions return the canonical KB answer from `faqs.json` / `policies.json` before retrieval, preventing hallucinated menu items.
* Simplify visible summary CTAs for reservable services: the user now sees only the full-itinerary option plus back, while the booking link remains inside the full itinerary and typed `reservar` behavior is preserved.
* Rename the itinerary booking block to a neutral booking-link label and keep referral/contact-only variants on their specialized summary flows.
* Mirror `Información > Actividades` to the current `Reserva` hierarchy: diving/snorkel tours, certified/beginner/mixed diving branches, course/go-pro/specialties structure, and the island `4 dives` variant.
* Add/update regression tests for canonical food answers, summary CTA behavior, and the new info-branch navigation/back behavior.

0.15.0 - (2026-05-28)
---------------------
* Cart-style mixed-group flow with item aggregation (same type/plan merges qty), dynamic emoji-button cart pick (no more "respond with number"), per-person + total-bold price breakdown, and snorkel filtered out of the cert+beg mixed branch.
* New LOCATION step with cost-aware prompt (Cartagena vs. islands shows price + transport-included note) inserted between service selection and COLOMBIAN for tours.
* Reservar button added to itinerary_offer and summary follow-up; booking links now only sent on Reservar click (not in summary), accompanied by single advisor message.
* Itinerary view splits into two chat messages via `MESSAGE_SPLIT` sentinel (itinerary + follow-up prompt with buttons).
* Beginner age question now has three options (under 8 / 8-10 Bubble Makers / 10+) routing to escalation or normal flow.
* Open Water origin prompt explains price for each location option. tours_certified copy emphasizes days (each option shows days + dives).
* Copy polish: "buceos" → "inmersiones" in menus; `U$` → `$` in mixed summary; Refresher line clarifies no extra cost; bioluminescence line expands description; Bubble Makers depth clarified ("máximo 2 metros de profundidad"); "asesor confirmará el precio final al reservar" replaces vague "cotización aparte"; escalate fallback no longer says "Para esta situación específica...".
* Servicio Privado now uses bilingual `price_note_es`/`price_note_en`; summary hides `✅ Incluye:` when service has no items.
* New cart-flow entry-path tracking (`mixed_entry_path: "diving_snorkel" | "cert_beg"`) drives both the activity menu filter and a separate cert+beg intro that no longer mentions snorkel.
* `mixed_add_cert_plan` shows brief description per option.
* `tools/intent_classifier.py` (new): LLM-based mapping of free text to button values for mixed-flow steps with currency-switch/restart/back/RAG fallback.

0.14.5 - (2026-05-26)
---------------------
* Set Cartagena certified `3 dives` back to `1 day` and align the guided flow, service IDs, and tests with the night-dive variant.
* Standardize lodging guidance for certified packages: main menu warning, per-package accommodation notes, and short `ℹ️` summary blocks that only state hotel/accommodation is not included.
* Keep island certified package variants consistent, including the 4-dives variant back-navigation and updated regression coverage for Cartagena/island summaries.

0.14.4 - (2026-05-23)
---------------------
* Split the PADI booking flow into separate Go Pro and Specialties submenus, with guided access to Advanced, Rescue + EFR, Divemaster, and each specialty.
* Keep summary/itinerary follow-up inside `SUMMARY`, add a `🔙 Volver` / `🔙 Back` button there, and preserve the correct return target for each course menu.
* Refine Divemaster as a contact-only program: richer localized summary/itinerary copy, info link instead of booking link, and a direct Contact/Book CTA that escalates cleanly.
* Update decision-tree and conversation tests for the new PADI navigation and Divemaster contact flow.

0.14.3 - (2026-05-23)
---------------------
* Reorganize the tours booking flow so, after choosing Cartagena vs. islands, users choose the activity first: diving, snorkeling, or mixed group.
* Route snorkeling directly to the snorkeling service flow, and keep diving-specific decisions inside a new diving submenu (certified / beginners / mixed certified+beginners).
* Simplify the diving beginner branch so `Only beginners` goes straight to the minicourse age check; remove the private-service option from that branch.
* Align Spanish/English copy, quick replies, and back-navigation with the new tours structure.
* Update decision-tree and conversation regression tests for the new tours paths and beginner direct-routing behavior.

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
