# Session handoff

Read this file before changing code in the Diving Planet Bot. For a quick version overview, read `docs/HISTORY.md` first.

## Current branch and workflow

- Main collaboration branch: `feature/dev_alvaro` (Gadea trabaja en `feature/dev_gadea` y se mergea periódicamente).
- Always start with `git status --short --branch` and check whether the branch is ahead/behind the remote.
- Use `/start-context` at the beginning of a session and `/close-work` before committing/pushing.
- `/close-work` must review this file and update it whenever architecture, workflow, risks, validation, current product context, environment details, or next-session priorities changed.
- Do not mix unrelated work in the same commit; keep decision-tree, RAG, infrastructure, and data-cleanup changes separated when possible.

## Architecture snapshot

1. Chatwoot sends webhooks to `/webhooks/chatwoot`.
2. `src/channels/chatwoot.py` extracts user input, manages in-memory `ConversationState`, routes through the supervisor, and sends replies back to Chatwoot.
3. `src/agents/supervisor.py` routes between deterministic decision tree, RAG, and escalation.
4. `src/flows/decision_tree.py` owns menu states, quick replies, booking summaries, and deterministic flows; it loads service details from `data/knowledge_base/services.json`.
5. `src/agents/rag_agent.py` answers free text using sanitized knowledge-base content through `src/knowledge/vector_store.py`.

- Real Chatwoot `input_select` buttons replaced numeric menu text in the decision tree.
- Button clicks are processed by reading `submitted_values`; a poller exists because local Chatwoot may not emit incoming webhooks for clicks.
- Polling also handles missed incoming messages, with deduplication to prevent double replies.
- Gadea expanded the decision tree, knowledge base, WhatsApp import tooling, retrieval/vector-store logic, and privacy handling.
- RAG was reconciled to preserve PII handling and previous history-aware retrieval/fallback behavior.
- Decision tree pricing (`PRICING_MENU`) and logistics (`LOGISTICS_MENU` + `ISLAND_MENU` / `ISLAND_HOTEL_MENU`) menus were refined based on real conversations: clearer options for salidas desde Cartagena vs. clientes ya en las islas, paquetes 5/7/9 buceos (incluido ahora 9 buceos (islas) en el bloque de precios), y submenús de logística (punto de encuentro/horarios, alojamiento/recogida, qué incluye/no incluye y qué llevar). `docs/arbol_opciones_es.md` y `TODO.md` se actualizaron para reflejar estos cambios.
- `services.json` is now the source of truth for service names, prices, inclusions, requirements, itineraries, and booking links used by the decision tree. The tree maps base services to `*_already_on_island` variants when the user is already in the islands and now exposes PADI specialties in the guided course menu.
- Raw WhatsApp exports and backups are treated as sensitive and should stay ignored/untracked.
- Country flag emojis (🇨🇴, 🇺🇸) do not render on Windows — replaced throughout with 🌎/🌐 for cross-platform compatibility.
- `src/agents/lead_summary.py` builds structured private Chatwoot notes on escalation; `state.pending_note` holds the note until sent in `chatwoot.py`.
- Lead notes are sent for all escalation types: keyword (`humano`, `agente`...), sensitive (medical, weather, complaints), and tree-internal escalation.
- `chatwoot.py` now performs the real human handoff by calling `escalate_to_human()` after sending the private lead note; `pending_escalation_reason` is only cleared when Chatwoot confirms the status toggle, so failed handoffs can be retried on later activity.
- `.claude/commands/runtests.md` provides a `/runtests` skill to run the conversation dataset with block-level keyword filtering.
- `chatwoot.py` auto-assigns new conversations to the owner agent (`CHATWOOT_OWNER_AGENT_ID` in `.env`) via `POST /conversations/{id}/assignments` AND toggles them to `open` via `POST /conversations/{id}/toggle_status` so they appear in the agent inbox instead of getting stuck in Pending. Set `CHATWOOT_OWNER_AGENT_ID=0` to disable.
- `chatwoot.py` dedupe: incoming text messages now check `{conversation_id}:{message_id}:incoming` before processing so Chatwoot's `message_created` + `message_updated` pair for the same id no longer produces double replies. Button echoes are still suppressed via `conversation_pending_echo_titles`.
- `supervisor.py` routing hardening: `_matches_escalation_keyword` uses word-boundary regex to prevent "persona" false positive; `_is_substantive_free_text` strips trailing punctuation so "hey?" routes to welcome; any bare greeting mid-flow (hola, hi, buenas…) resets state to WELCOME step.
- `supervisor.py` natural-language menu navigation: `_match_quick_reply_text` compares free text against the CURRENT `state.quick_replies` (not all BUTTON_OPTIONS) and, when it confidently matches a button, feeds the button value into the decision tree. Accent-insensitive via `_strip_accents` (NFD). Question words (`cuánto/how/what`…) short-circuit to RAG to avoid hijacking real questions.
- `supervisor.py` language-intent: `_detect_language_intent` recognises "english/ingles" and "spanish/espanol/castellano" anywhere in the message; at LANGUAGE step it picks the language and advances to MAIN_MENU, mid-conversation it switches `state.language`, acknowledges in the new language and re-shows the main menu.
- Two-level main menu: after language selection the user picks 🤿 Reservar or ℹ️ Información; Reservar → tours-de-buceo/snorkel OR cursos PADI; Información → precios / reservas y pago / logística. New `Step.RESERVA_MENU`, `Step.INFO_MENU`, `Step.TOURS_LOCATION`, `Step.BEGINNER_AGE`.
- Tours booking flow is now activity-first after location: `TOURS_LOCATION` → `GROUP_TYPE` (`diving / snorkeling / mixed diving+snorkeling`). Choosing diving opens `TOURS_EXPERIENCE` (`certified / beginners / mixed certified+beginners`). Snorkeling goes directly to the snorkeling service flow.
- PADI courses are split into focused submenus: `COURSES_ADVANCED_MENU` (Advanced / Rescue + EFR / Divemaster) and `COURSES_SPECIALTIES_MENU` (Mindful Diving, Fish ID, Naturalist, Buoyancy, Nitrox). Back navigation from summaries returns to the correct originating course menu.
- Info-leaf responses (pricing/booking/logistics) append a "back to menu" hint built by `DecisionTree._back_to_menu_hint`, paired with main_menu quick replies, so users can navigate to Reservar without re-greeting.
- Reservar branch has explicit "🔙 Volver" buttons (value=`back`) on every screen (reserva_menu, tours_location, group_type, tours_experience, tours_certified incl. island variant, tours_beginner compatibility step, beginner_age, courses_menu, courses_open_water_origin, courses_open_water_time, courses_advanced_menu). Yes/no qualifier screens (certified_last_dive, certified_experience, refresher_interest) intentionally omit the back button — they are flow control, not branch choices.
- `supervisor.py` splits menu keywords: `MENU_KEYWORDS` (`menu/inicio/start/opciones`) resets to MAIN_MENU; `BACK_KEYWORDS` (`volver/back/atras/atrás/regresar`) goes ONE STEP up via the `BACK_STEP` map (`_go_back_one_step`). When the current step has no mapping (e.g. SUMMARY/FREE_TEXT) the back keyword falls back to MAIN_MENU. The fuzzy text-to-button matcher routes "back" matches through the same back handler so the button works whether the user clicks it or types its title.
- Summary follow-up now stays inside `Step.SUMMARY` via `summary_mode`, including a dedicated `back` quick reply on itinerary-offer and follow-up states, so course summaries can show the itinerary, answer follow-up questions, and still return to the right menu without resetting the conversation.
- Visible summary CTAs for normal reservable services were simplified again: `itinerary_offer` now shows only `Ver itinerario completo + link de reserva` + `Volver`; typed `reservar` / `booking` input is still supported inside `SUMMARY`, and the booking link is rendered only in the full itinerary block.
- Divemaster is now treated as `contact_only` in `services.json` and the decision tree: summary and itinerary use localized intro/overview blocks, show the website as an info link instead of an online booking CTA, and expose a `Contactar/Reservar` path that escalates directly to the manager with a single non-duplicated confirmation message.
- `Información > Actividades` was brought in line with the current booking hierarchy. After location, the user now goes through mirrored activity submenus (diving/snorkel tours, certified/beginners/mixed diving branches, PADI courses → go pro / specialties / referral), but each leaf still returns an informational card instead of entering the booking flow.
- Info detail screens (`INFO_*_DETAIL`) now use `back_step_override` too, so back navigation returns to the exact originating info submenu, including the island-only certified `4 dives` variant selector.
- RAG system prompt (ES + EN) has an explicit DIVE TO HEAL exception: disability/accessibility questions about the adaptive diving program are answered with factual program info, not escalated as medical.
- `src/agents/rag_agent.py` now short-circuits food / lunch / dietary questions to a canonical answer built from curated FAQ/policy entries before similarity search, preventing hallucinated food answers.
- `load_embeddings.py` now indexes `pricing.json` fully (8 origin × section pairs × 2 langs + 2 discount_policy docs = 441 total KB documents) and includes COP prices in `services.json` embeddings.
- Mixed-group cart flow (`src/agents/intent_classifier.py` + MIXED_* steps in decision_tree): items of the same type/plan now aggregate into a single line. Modify/remove pick use dynamic emoji buttons (`1️⃣ 2 × Buceo certificado` + `🔙 Cancelar`) instead of free-text "respond with number". `ConversationState.mixed_entry_path` ("diving_snorkel" | "cert_beg") drives the activity menu filter (snorkel hidden in cert+beg) and a separate `mixed_entry_cert_beg` intro that does not mention snorkel.
- Mixed summary refactored: per-person + total-bold formatting (`*qty × label*` + `qty × $price p.p. = *$total*`), `$` instead of `U$`, includes shows only when there are items. Booking links are NOT in the summary anymore — they are stored in `state.mixed_booking_links` and sent only when the user clicks the `📝 Reservar` button.
- Sequential location/Colombian for tours: `_goto_location_with_costs` puts the user through LOCATION (with bilingual cost-aware prompt: "Desde Cartagena $X / Ya en las islas $Y") → COLOMBIAN → SUMMARY. If `state.location` is already set (tests, restored conversation), LOCATION is skipped and the flow goes straight to COLOMBIAN.
- New `📝 Reservar` button on `itinerary_offer` (and on `summary` follow-up after "Ver itinerario completo"). On click: escalates to advisor + sends booking link (10% off) inline — for Colombian users the link is omitted and the advisor coordinates the discount. Removed `🙏 No gracias`.
- Itinerary view split: full itinerary and follow-up prompt are sent as two separate chat messages via `MESSAGE_SPLIT` sentinel. `src/channels/chatwoot.py` detects the sentinel and dispatches two messages (quick_replies only on the last one).
- Tours certified menu: items renamed "Buceos" → "Inmersiones" and copy of the question emphasises days. Open Water origin shows price for each option.
- Beginner age question: 3 buttons now (`👶 menores de 8` → escalate snorkel only; `👦 8-10 Bubble Makers` → escalate; `🧑 todos 10+` → normal flow). Bubble Makers wording clarified to "máximo 2 metros de profundidad".
- `_handle_reserva_menu`: choice 1 (Tours) now goes directly to GROUP_TYPE — the deprecated TOURS_LOCATION step is bypassed (the location question moved to LOCATION between service selection and COLOMBIAN).
- `mixed_add_cert_plan` ahora describe brevemente cada opción (2 inmersiones / 1 día vs. multi-día). `mixed_cart_modify_pick` y `mixed_cart_remove_pick` ya no piden número en texto.
- `MESSAGES["escalate"]` reescrito: "Te paso con un asesor del equipo de Diving Planet" (sin "humano", sin "Para esta situación específica..."). Mismo cambio aplicado en RAG fallback y broken-link complaint.
- Servicio Privado: `services.json` ahora tiene `price_note_es`/`price_note_en` bilingüe y la sección "✅ Incluye:" del summary se oculta cuando el servicio no tiene items.

## Current product context

- The bot supports Spanish/English decision-tree flows and free-text RAG answers.
- Chatwoot buttons are sent as `input_select` quick replies, while numeric/text fallback still works.
- Local Chatwoot may not always emit incoming webhooks for button clicks, so the bot includes polling/deduplication logic.
- The decision tree has recently been improved for:
  - Cartagena certified 2 dives / 1 day.
  - Summary flow: initial summary is short and offers an optional full itinerary; the itinerary offer is handled in `Step.SUMMARY` with `summary_mode`, supports `back`, and only then transitions to `FREE_TEXT` when the user chooses to ask more. The visible CTA for regular services is now itinerary-only (`Ver itinerario completo + link de reserva` + `Volver`), while typed `reservar` still works. 3 buceos (islas) pasó a "core split" (pide última inmersión y nacionalidad antes del resumen), igual que 2/5/7/9.
  - Certified package standardization: Cartagena `3 dives` is again `1 day` (2 daytime + 1 night dive), and all certified multi-day/night-dive packages now show explicit island-accommodation requirements in menus, summaries, and itinerary/detail views.
  - Certified summary `ℹ️` blocks for Cartagena/island packages were shortened so they emphasize only that hotel/accommodation is not included, instead of repeating long descriptive text.
  - Tours branch restructure: after location the user chooses diving / snorkeling / mixed; snorkeling is direct and diving has its own certified/beginners/mixed submenu.
  - Cartagena diving beginners: `Only beginners` now goes directly to the minicourse age question (no private-service option in that branch).
  - Cartagena certified multi-day packages: 5/7/9 dives, lodging/nocturnal notes, and refresher handling.
  - Island-based certified and beginner service variants from `services.json`.
  - PADI advanced/professional courses and specialties, now separated into Go Pro vs. Specialties submenus.
  - `Información > Actividades` now mirrors the updated booking hierarchy, including correct back-navigation from info detail cards and the island `4 dives` variant path.
  - Divemaster contact-only selling flow with richer summary/itinerary copy and manager handoff CTA.
  - Food-related free-text answers now come from canonical KB copy before retrieval, so lunch/dietary responses stay deterministic.
- `faqs.json` has been expanded with curated educational diving content for beginners, safety, equipment, course comparisons, underwater sensations, marine-life etiquette, and Rosario Islands destination knowledge.
- Current MVP direction: inform, qualify, recommend, and prepare human-assisted conversion; do not automate live availability, payment, or final booking confirmation yet.
- Conversation-state migration from in-memory storage to Redis/PostgreSQL is intentionally deferred during dev; treat it as a last hardening step right before moving to PRE.
- Use `docs/mvp-intent-matrix.md` and `docs/kb-audit-mvp.md` before expanding tree/RAG behavior.
- `docs/infra-simple.excalidraw` contains the current minimal infrastructure scheme for team communication.
- Mixed groups, private services, pricing, booking/payment, **cancellation/change rules** (major KB gap — needs owner confirmation), and logistics constraints by hotel/island are still areas for systematic polishing.
- COP pricing is now in the KB; bot needs a restart in WSL2 to serve it after the re-index run. Embeddings reindex done (445 docs) para incluir nuevos servicios y ajustes de precios.
- `CHATWOOT_OWNER_AGENT_ID=1` should be added to `.env` (owner agent ID confirmed via `/api/v1/profile`).
- Next session priorities:
  - Live E2E retest of the new cart-style mixed-group flow after server restart (item aggregation, emoji modify/remove buttons, snorkel-hidden in cert+beg, restaurant-bill summary, Reservar sends booking links + advisor msg).
  - Live E2E retest of the tours `Reservar` button on regular itinerary_offer (sends booking link + advisor message; link omitted for Colombian users).
  - Live E2E retest of `Información > Actividades` in the Chatwoot widget, especially diving → certified → island `4 dives` and back-navigation from each informational card.
  - Live E2E retest of the LOCATION step (Cartagena/Islas with cost-aware prompt) for cert/snorkel/beginner branches — investigate user-reported "location not asked" bug (may be stale state).
  - Live E2E investigation of user-reported "Colombian asked twice" in diving flow — need an exact transcript to reproduce.
  - Apply same sequential LOCATION/COLOMBIAN deferral pattern to PADI courses (Open Water origin question has cost context, but Advanced/Specialties/Referral go COLOMBIAN inline — should adopt the same `_goto_location_with_costs` pattern for consistency).
  - Verify "Ver itinerario completo" actually splits into two messages on Chatwoot widget (MESSAGE_SPLIT sentinel handling).
  - Investigate user-reported "stuck" bugs at MIXED_FINAL_KIDS and MIXED_FINAL_PRIVATE — likely state-loss on server restart (in-memory `conversations` dict); persistent state store would fix it but is deferred to pre-PRE hardening.
  - Investigate "cuánto es el precio en euros?" routing to escalation — RAG should answer with current exchange context, not escalate.
  - Live E2E retest of certified dive package summaries in Chatwoot (especially Cartagena `3 dives (1 day)` and island variants) to confirm the short `ℹ️` block and lodging notices render correctly.
  - Live E2E retest of the PADI course menus in the Chatwoot widget (Go Pro vs. Specialties, back button from summary/itinerary, and Rescue + EFR emoji rendering on Windows).
  - Live E2E retest of the Divemaster contact-only flow in the widget (summary CTA, itinerary CTA, single escalation message, and lead note delivery).
  - Live E2E retest of the new menu structure (Reservar/Información), fuzzy text matching, and mid-conversation language switch in the Chatwoot widget.
  - RAG content gaps surfaced during testing: Dive Master is missing from the "cursos" answer; output formatting of multi-section RAG answers needs review (markdown not rendering line breaks properly in the widget).
  - Optional: bulk-assign old NULL-assignee_id conversations in dev Chatwoot DB to clean the inbox (`UPDATE conversations SET assignee_id=1 WHERE assignee_id IS NULL;`) — pending user confirmation.
  - Cancellation/payment policy KB completion.
  - PRE deployment checklist.
  - Live E2E test of COP price answers after bot restart.

## Knowledge base and privacy

- Versioned KB lives under `data/knowledge_base/` and must be curated/sanitized.
- Important KB files: `services.json`, `faqs.json`, `policies.json`, `pricing.json`, `availability.json`, `conversations.json`, `brand_tone.json`.
- Treat `faqs.json` as curated public-facing content: keep new entries bilingual, consolidated by topic, and avoid adding medical clearance, live availability, unsanitized customer details, or unverified booking/payment claims.
- Never stage raw exports or private customer data:
  - `wasap/`
  - raw `_chat.txt` exports
  - voice/photo/sticker/contact/PDF exports
  - `data/knowledge_base/*.bak`
  - `data/knowledge_base/*pre_dedup*`
  - real private payment links, IDs, phone numbers, emails, documents, or customer-identifying content unless sanitized.

## Standard validation

Run after meaningful code changes:

```powershell
python -m pytest tests/test_chatwoot_buttons.py tests/test_decision_tree.py tests/test_rag_safety.py
python -m compileall src tests
```

If retrieval, embeddings, or vector-store behavior changes, also run:

```powershell
python -m pytest tests/test_retrieval_rerank.py
```

## Dev environment notes

- Bot runs in WSL2 Ubuntu on port 8000: `python -m src.main` (with conda base active).
- Chatwoot runs in Docker on port 3300: `docker compose --profile chatwoot up -d`.
- Chatwoot webhook is configured in the DB (`chatwoot_dev.webhooks`) pointing to `http://host.docker.internal:8000/webhooks/chatwoot`.
- Webhook subscriptions must include `message_created`, `message_updated`, `conversation_created`, `conversation_status_changed`. Missing `message_updated` means button clicks are ignored.
- `host.docker.internal` from Docker resolves to `192.168.65.254` (Docker Desktop host), which reaches WSL2 bot via Docker Desktop port bridging.
- `CHATWOOT_BASE_URL=http://localhost:3300` in `.env` is correct for bot→Chatwoot API calls from WSL2.
- To verify webhook config: `docker exec dp-dev-postgres psql -U postgres -d chatwoot_dev -c 'SELECT id, url, subscriptions FROM webhooks;'`
- `chatwood-test.html` is **gitignored** (contains personal Chatwoot tokens per developer). Each developer keeps their own local copy with their inbox's websiteToken; do not re-add it to the index. To get the website widget token, query the Chatwoot API: `curl -H "api_access_token: <YOUR_TOKEN>" http://localhost:3300/api/v1/accounts/1/inboxes`. The file also has SDK onerror/retry + status bar so the widget surfaces clear errors when Docker/Chatwoot is unreachable instead of failing silently.
- Refresher handling in the cart-style mixed-group flow now produces a free line item (`type: "refresh"`) that is hidden from the paid rows of `_format_mixed_final_summary` and rendered as `🧑‍🏫 Refresher incluido: N personas — sin coste adicional` inside the EXTRAS block. The mixed flow asks both about interest AND about quantity (`MIXED_CERT_REFRESH_INTEREST` → `MIXED_CERT_REFRESH_QTY`). The companion-from-single flow now mirrors this with a `mixed_from_single_refresher_qty_pending` step (asks qty for 2+ certified divers, auto=1 for single companion) and `group_context["refresher_qty"]`. `_enter_mixed_flow_from_single` adds both the speaker's refresher (when `state.refresher_interested` was set during the original 2-dives flow) and the companion refresher quantity as one combined `refresh` cart line. `REFRESHER_PRESERVE_SERVICES` now includes `2_dives_1_day` and its island variant, so accepting a refresher in the single 2-dives flow does NOT swap the service to minicourse — it stays as buceo certificado with an annotation. Cart label for refresh items is "Refresher (sin coste)".

## Manual Chatwoot checks

When touching Chatwoot, buttons, routing, or conversation state:

- Start the bot: `python -m src.main` in WSL2 Ubuntu (conda base).
- Start Chatwoot: `docker compose --profile chatwoot up -d`.
- Open `chatwood-test.html` in a browser.
- Test `hola` → language buttons (🌎 Español / 🌐 English).
- Click `Español` → main menu buttons (🤿 Reservar / ℹ️ Información).
- Type `reservar` (text instead of clicking) → must advance to RESERVA_MENU (fuzzy text match).
- Type `in english` or `me lo puedes decir en español?` mid-conversation → must switch language and re-show main menu.
- Send free text from a menu → RAG response without duplicate replies.
- After a pricing/booking/logistics answer, confirm the back-to-menu hint appears and quick replies are main_menu.
- At any Reservar step, click `🔙 Volver` → must go ONE step up (e.g., TOURS_CERTIFIED → TOURS_EXPERIENCE), not all the way to MAIN_MENU.
- Type `volver` or `atrás` mid-Reservar → same one-step-up behaviour as the button.
- Click through at least one full booking path.

## Where to look first

- `docs/HISTORY.md`: version-level overview.
- `docs/mvp-intent-matrix.md`: commercial intent ownership across tree, RAG, and human handoff.
- `docs/kb-audit-mvp.md`: current KB coverage and gaps for MVP robustness.
- `docs/infra-simple.excalidraw`: simple current infrastructure diagram.
- `src/flows/decision_tree.py`: deterministic flow and service catalog.
- `tests/test_decision_tree.py`: expected decision-tree behavior.
- `src/agents/supervisor.py`: routing rules.
- `src/agents/rag_agent.py`: free-text answering and safety prompt.
- `src/channels/chatwoot.py`: webhook, polling, and message sending.
- `TODO.md`: current product backlog and branch-polishing checklist.
