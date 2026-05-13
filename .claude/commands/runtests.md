---
description: Run the full test suite and report results with pass/fail summary
---
# Run tests

Execute this workflow to validate the bot after any code change.

1. Run the full test suite:

```powershell
python -m pytest tests/ -v --tb=short 2>&1
```

2. Capture the result and report:

- Total tests passed / failed / errors.
- If any tests fail, show the test name, the assertion that failed, and the likely cause.
- If all pass, confirm the count and that the suite is green.

3. If failures exist:

- Group them by category (tree logic, escalation, RAG routing, lead summary, safety).
- For each failure explain in one line what broke and suggest the most likely fix.
- Do NOT auto-fix unless the user explicitly asks.

4. If the user wants to run only a specific block, they can pass a keyword:

```powershell
python -m pytest tests/test_conversations.py -k "<keyword>" -v --tb=short
```

Available keywords (map to test blocks):
- `language` — Bloque 1: primer contacto e idioma
- `certified` — Bloque 2: buzos certificados Cartagena
- `beginner` — Bloque 3: principiantes
- `island` — Bloque 4: ya en las islas
- `mixed` — Bloque 5: grupo mixto
- `course` or `open_water` or `advanced` — Bloque 6: cursos PADI
- `pricing` — Bloque 7: precios
- `booking` — Bloque 8: reservas y pagos
- `logistics` — Bloque 9: logística
- `hotel` or `selector` — Bloque 10: selector isla/hotel
- `escalat` — Bloque 11: escalaciones
- `medical` or `weather` or `complaint` — Bloque 12: escalaciones sensibles
- `pii` — Bloque 13: privacidad
- `rag` or `free_text` — Bloque 14: enrutamiento RAG
- `en_` — Bloque 15: flujos en inglés
- `lead_summary` or `lead_note` — Bloque 16: resumen de lead
- `invalid` or `robustez` — Bloque 17: opciones inválidas
- `quick_replies` — Bloque 18: quick replies

5. After reporting, ask the user if they want to run a specific block or fix a failure.
