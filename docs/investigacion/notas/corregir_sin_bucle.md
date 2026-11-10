# Cómo mantienen y mejoran los equipos maduros un agente de atención al cliente sin caer en el bucle de parches

Notas de investigación (10-nov-2026). Fuentes primarias siempre que ha sido posible; las de vendor están marcadas como tales (marketing). Material anterior a 2025 marcado como «(antiguo)».

Resumen en una frase: los equipos maduros no «arreglan casos», sino que (1) leen conversaciones reales con un experto de dominio, (2) agrupan los fallos en familias y cuentan cuántos hay de cada una, (3) deciden por tipo de fallo a qué artefacto va la corrección (conocimiento → procedimiento en lenguaje natural → herramienta/código → prompt, en ese orden de preferencia), (4) convierten cada fallo en un test de regresión, (5) versionan todo como código (snapshot inmutable, diff, revisión por pares, simulaciones obligatorias, canary, rollback) y (6) miden en un conjunto apartado que no se usa para afinar.

---

## 1. ¿Cuál es el bucle diario tras el lanzamiento en Sierra, Decagon, Intercom, Ada y Parloa? (quién revisa, con qué frecuencia, qué artefacto cambia, cómo se prueba antes de soltar)

### Takeaway
Los cinco vendors convergen en el mismo esquema: el equipo de CX (no ingeniería) revisa muestras de conversaciones a diario o semanalmente y anota «qué debió pasar»; cada anotación se convierte en un test; los cambios (conocimiento, procedimientos en lenguaje natural, herramientas) se hacen en un *workspace*/rama aislada, se prueban con tests unitarios y simulaciones, pasan revisión y salen como versión inmutable con rollout parcial y rollback. Todo es material de vendor; nadie publica cifras independientes de eficacia.

### Cited Findings

**Sierra**
- (antiguo, jun-2024) Revisión diaria por CX: «Customer experience teams formally evaluate samples of conversations every single day, annotating the conversations with feedback». Se exige experto de dominio: «Knowing whether an AI agent behaved correctly requires a subject matter expert». — [Sierra, Agent development life cycle](https://sierra.ai/blog/agent-development-life-cycle)
- Cada conversación anotada se convierte en test con APIs simuladas: «these annotated conversations become the basis for the agent's regression tests»; los tests corren «in parallel during development and prior to every agent release». — [Sierra, ADLC](https://sierra.ai/blog/agent-development-life-cycle)
- Versión = snapshot inmutable: «each agent release is a snapshot that includes not only the underlying source code and prompts, but model version dependencies and an immutable snapshot of all of the knowledge available to the agent»; rollback instantáneo y A/B entre releases. — [Sierra, ADLC](https://sierra.ai/blog/agent-development-life-cycle)
- (antiguo, jul-2024) Reparto de roles: «CX teams will review conversations for quality assurance while technical teams debug integrations and provision APIs»; reunión semanal con stakeholders «to review performance, ship updates, and prioritize new journeys»; tras un error, los clientes «generate tests to make sure they never make the same mistake twice». — [Sierra, Shipping and scaling AI agents](https://sierra.ai/blog/shipping-and-scaling-ai-agents)
- (ago-2026) Gobernanza de releases: «Organizations can now require peer review before any change releases»; «Reviewers can inspect line-by-line diffs, leave contextual comments, and request changes before a merge is approved»; rol Reviewer (CX lead, compliance, eng manager…); se puede exigir «Simulations to pass before moving toward production»; «Agent Checks» actúa como linter; split-traffic («incrementally roll out a release to a portion of customer traffic before expanding it to everyone»); «every release is an immutable snapshot, rolling back is just as fast». — [Sierra, Release governance](https://sierra.ai/blog/release-governance-guardrails-for-agents-at-scale)
- Workspaces como ramas: «a Workspace works like a collaborative draft, or a feature branch for your agent». — [Sierra, Workspaces](https://sierra.ai/uk/blog/workspaces) (snippet de búsqueda)

**Decagon**
- (nov-2025) Cada edición de AOP, herramienta o guideline es un commit: «applies CI/CD principles to ensure every AOP, tool, and guideline edit is tracked as a versioned commit»; «every change is traceable, reviewable, and reversible»; «Each commit triggers alerts summarizing who made changes and linking to Git diffs». — [Decagon, Agent Versioning](https://decagon.ai/blog/decagon-agent-versioning)
- Workspaces aislados (prod/staging/custom), aprobación configurable («approval-based for regulated environments»), «Changes can be tested with unit tests or Simulations before being published to production»; se puede ver «which agent version handled a specific conversation»; comparar CSAT/deflection entre versiones. — [Decagon, Agent Versioning](https://decagon.ai/blog/decagon-agent-versioning)
- Quién toca qué: «Developers can manage versions directly in GitHub, while product and CX teams can do the same in the Decagon console»; «It turns what was once a DevOps-only process into a shared system of record». — [Decagon, Agent Versioning](https://decagon.ai/blog/decagon-agent-versioning)
- (jul-2025) Los AOP los escribe CX en lenguaje natural: «AOPs empower CX teams to design complex, multi-step workflows entirely in natural language»; las simulaciones «can also be scheduled to run automatically, catching regressions or subtle drift». — [Decagon, The future of AI agents is test-driven](https://decagon.ai/blog/the-future-of-ai-agents-is-test-driven)
- Dos tipos de prueba: «Message Replays let you run focused unit tests on specific agent responses, perfect for validating a bug fix or testing a small AOP tweak» y Simulations con personas sintéticas en conversaciones completas; «Because AI agents are non-deterministic, running tests multiple times is essential»; simulaciones «before go-live, after launch, and before any major update to AOPs or knowledge». — [Decagon, Simulations](https://decagon.ai/blog/decagon-simulations) (snippets de búsqueda)
- (oct-2026, snippet) Experiment Hub: bloques de experimento dentro de un AOP, cada variante validada en Simulations «against a golden test set before any live traffic». — [Decagon, Experiment Hub](https://decagon.ai/blog/experiment-hub)

**Intercom (Fin)**
- Orden de artefactos: «Fin always generates answers from your content first. Guidance should only be used to refine or structure those answers further»; «Guidance → Refine how the answer is phrased (specific tweaks)»; «Procedures → Handle complex or multi-step interactions». — [Intercom, When to use Fin Guidance vs Procedures](https://www.intercom.com/help/en/articles/14623785-when-to-use-fin-guidance-vs-procedures)
- Prueba antes de publicar: probar en «Preview Mode», simular escenarios, panel de eventos (Cmd/Ctrl+E) para ver «how Fin evaluated each rule»; tratar la guidance como «an ongoing process» revisada contra métricas. — [Intercom, Fin Guidance best practices](https://www.intercom.com/help/en/articles/10560969-fin-guidance-best-practices)
- Límite duro: «There is a maximum of 100 active pieces of guidance per workspace»; «Each guidance rule is evaluated separately», «There's no built-in way to chain or cascade guidance automatically». — [Intercom, Fin Guidance best practices](https://www.intercom.com/help/en/articles/10560969-fin-guidance-best-practices)
- Propiedad: la doc no fija quién posee cada capa; solo recomienda un «shared task tracker» para «a clear overview of ownership and progress». — [Intercom, Mastering knowledge management](https://www.intercom.com/help/en/articles/11782981-mastering-knowledge-management-for-ai-first-support-with-fin) (snippet)

**Ada**
- (ene-2025) Coaching desde la vista de conversación: «Coaching lets you provide feedback on what your AI Agent says, thinks, and does». — [Ada release notes 7-ene-2025](https://docs.ada.cx/release-notes/2025/1/7)
- (ene-2025) El sistema valida la instrucción de coaching: «Your AI Agent will now automatically flag if your edited Coaching Intent is confusing or potentially problematic». — [Ada release notes 30-ene-2025](https://docs.ada.cx/release-notes/2025/1/30)
- (abr-2025) Revisión de cómo se aplicó el coaching en conversaciones nuevas: «you can now review how coaching is used in new conversations and quickly flag whether it was correctly considered». — [Ada release notes 28-abr-2025](https://docs.ada.cx/release-notes/2025/4/28)
- Diferencia Coaching vs Custom Instructions: «Coaching works best when defining specific changes in an AI Agent's past behavior based on the unique context of only some conversations. Custom Instructions work best when providing general instructions that apply to every conversation». — [Ada, Coaching](https://docs.ada.cx/docs/optimization/coaching) (snippet)
- Guía «problema → artefacto»: contenido ausente → artículo de conocimiento; necesita datos vivos o ejecutar algo → Action (API) / Playbook; intención correcta pero respuesta floja → Coaching «without changing its overall logic or retraining the model»; correcto pero genérico → Personalization. «The goal isn't to fix everything at once». — [Ada, Improvement tactics](https://docs.ada.cx/docs/welcome/improvement-tactics)
- Los inputs de coaching deben venir de conversaciones reales: «coaching inputs should come from actual customer conversations—not made-up use cases or hypothetical prompts». — [Ada blog, 5 ways to start coaching](https://www.ada.cx/blog/5-ways-to-start-coaching-your-ai-agent-for-optimal-performance/) (vendor)

**Parloa**
- (nov-2026) Config del agente en control de versiones: «Store agent settings in the version control they already use»; cada cambio se publica como versión y se promueve «from testing to live, with rollback as needed»; «Publishing and deployment remain separate actions»; «Teams that already use Parloa's automated testing can turn it into a required step in every release». — [Parloa, Agent Management API/SDK/CLI](https://www.parloa.com/blog/build-agents-your-way-introducing-parloa-s-agent-management-api-sdk-cli-and-mcp/)
- (oct-2026) Simulaciones antes de cada release, con expertos humanos confirmando primero que los escenarios reflejan el estándar de negocio. — [Parloa, Confidently release agent improvements](https://www.parloa.com/blog/confidently-release-agent-improvements-faster-with-automated-testing/) (snippet, vendor)
- (ago-2026) Enrutado de hallazgos a dueños: «Sends coaching moments, misrouted intents, and repeated questions to the human agents, AI agent configurators, and workflow owners responsible for the fix». — [Parloa, Conversation intelligence](https://www.parloa.com/knowledge-hub/conversation-intelligence/) (vendor)

### Inferences
- El patrón común es «git para el agente»: rama/workspace → diff → revisión → tests + simulaciones → snapshot inmutable → canary → rollback. Quien lo ha adoptado lo presenta como respuesta explícita a «nadie sabe quién decide» (Decagon: «shared system of record»; Sierra: rol Reviewer con nombre).
- La corrección no la hace quien detecta el fallo: CX anota, el artefacto cambia según el tipo (Ada e Intercom lo codifican como tabla de decisión), e ingeniería solo entra en integraciones/herramientas.
- Ninguno describe «parchear el prompt del sistema» como vía de corrección: el prompt base queda fuera del bucle diario; lo que se edita son conocimiento, guidance/coaching acotado o procedimientos.

### Gaps
- Ningún vendor publica tamaño de muestra diario de revisión ni tasa de regresiones evitadas; todo es material de marketing sin verificación independiente.
- Intercom no documenta quién posee Guidance vs Procedures ni un flujo de aprobación.
- No se encontró documentación de Sierra a nivel SDK (pinning de versiones, comandos del runner de tests).
- La página de coaching de Ada en docs/monitoring devolvió 404; la de best-practices solo mostró la introducción.

---

## 2. ¿Dónde va cada corrección (artículo de conocimiento vs procedimiento en lenguaje natural vs herramienta/código vs prompt) y quién es dueño de cada tipo de cambio?

### Takeaway
Las guías de vendor coinciden en una jerarquía de artefactos: primero conocimiento, luego una regla acotada en lenguaje natural (guidance/coaching) solo para afinar, luego procedimiento para flujos de varios pasos, y herramienta/código para datos vivos o acciones; el prompt global queda como último recurso. El dueño por capa casi nunca está escrito; Sierra y Decagon describen el reparto CX (contenido, AOPs, revisión) vs ingeniería (integraciones, versiones en GitHub).

### Cited Findings
- Intercom, prueba rápida: «if your rule is 'if X, do Y' or 'if X, escalate' — use escalation guidance» y «if your rule is 'if X, first do A, then B, then C' — use a procedure». Guidance es «best for small, specific changes to how Fin communicates». — [Intercom, Guidance vs Procedures](https://www.intercom.com/help/en/articles/14623785-when-to-use-fin-guidance-vs-procedures)
- Intercom, por qué no meter lógica en guidance: se aplica durante la generación, «Only part of your instructions may be included» y los pasos pueden saltarse o reordenarse. — [Intercom, Guidance vs Procedures](https://www.intercom.com/help/en/articles/14623785-when-to-use-fin-guidance-vs-procedures)
- Intercom, regla de «no sé la respuesta → escala» no funciona en guidance «because guidance is checked before Fin searches your content»; la guidance «can be unreliable across longer conversations» (mejor en una sola vuelta). — [Intercom, Guidance best practices](https://www.intercom.com/help/en/articles/10560969-fin-guidance-best-practices)
- Ada: Knowledge para «Generic replies caused by missing, outdated, or unclear content»; Actions «when static answers aren't enough»; Playbooks para flujos que «collect inputs, apply logic, and trigger Actions»; Coaching para intención correcta con respuesta floja. — [Ada, Improvement tactics](https://docs.ada.cx/docs/welcome/improvement-tactics)
- Decagon: CX escribe AOPs en lenguaje natural «without relying on back-and-forth with external professional services». — [Decagon, test-driven](https://decagon.ai/blog/the-future-of-ai-agents-is-test-driven)
- Sierra: un «dedicated agent engineer and product manager on each deployment», «responsible for translating the journey design into agent code»; CX revisa calidad, técnicos «debug integrations and provision APIs». — [Sierra, Shipping and scaling](https://sierra.ai/blog/shipping-and-scaling-ai-agents) (antiguo, jul-2024)
- Hamel Husain: «The most successful teams flip this model by giving domain experts tools to write and iterate on prompts directly»; «the people best positioned to improve your AI system are often the ones who know the least about AI». — [Hamel, Field Guide](https://hamel.dev/blog/posts/field-guide/)
- Hamel, quién anota: un solo experto de dominio como «benevolent dictator» que «can incorporate input and feedback from others, but they drive the process»; «Start with a benevolent dictator whenever feasible». — [Hamel, Evals FAQ](https://hamel.dev/blog/posts/evals-faq/)
- Anthropic, sobre herramientas: «offload agentic computation from the agent's context back into the tool calls themselves»; «Tools can consolidate functionality, handling potentially multiple discrete operations (or API calls) under the hood»; «One of the most common failure modes we see is bloated tool sets that cover too much functionality». — [Anthropic, Writing effective tools](https://www.anthropic.com/engineering/writing-tools-for-agents) (sep-2025); [Anthropic, Context engineering](https://www.anthropic.com/research/effective-context-engineering-for-ai-agents) (sep-2025)

### Inferences
- La «tabla de decisión» de Ada e Intercom es la práctica concreta de «arreglar por familia»: antes de tocar nada se clasifica el fallo (falta de contenido / falta de datos / tono / flujo) y la clase determina el artefacto. Un fallo de contenido nunca se corrige con una regla de prompt.
- Dueño implícito: contenido y guidance/coaching → CX ops; procedimientos/AOPs → CX con revisión; herramientas, integraciones y prompt base → ingeniería. Intercom y Ada diseñan la UI para que CX no necesite ingeniería, lo cual es a la vez práctica y argumento de venta.

### Gaps
- Ninguna fuente prescribe explícitamente «quién puede editar el prompt del sistema»; se deduce de que las UIs de vendor no lo exponen a CX.
- No se encontró ningún estudio independiente que compare eficacia de corregir vía conocimiento vs vía instrucción.

---

## 3. ¿Qué dicen los practicantes (Husain, Shankar, Yan, Liu, Huyen) sobre análisis de errores, taxonomías de fallo y no sobreajustar al conjunto de evaluación? Reglas concretas

### Takeaway
Reglas repetidas por todos: mirar los datos a mano antes de medir nada (≥30 trazas propias, ~100 en el pool); construir la taxonomía desde la revisión humana y contar fallos por categoría para atacar la familia más frecuente; arreglar primero los huecos obvios y solo después automatizar un evaluador por modo de fallo; dividir las etiquetas en train/dev/test y tocar test una sola vez; no usar métricas genéricas; rehacer el análisis de errores con cada cambio grande porque los criterios «derivan».

### Cited Findings
- «Error analysis is the most important activity in evals»; pasos: dataset → open coding → axial coding → refinar; «Start by annotating at least 30 traces yourself before reviewing suggestions from an agent»; anotar el *primer* fallo de cada traza porque «upstream errors can cause downstream issues»; «Axial coding is the most important step»; «At the end, count the number of failures in each category»; iterar «until you reach theoretical saturation, meaning new reviews stop revealing failure modes or changing existing ones»; «A working pool of roughly 100 diverse traces is a useful guardrail». — [Hamel, Why is error analysis so important](https://hamel.dev/blog/posts/evals-faq/why-is-error-analysis-so-important-in-llm-evals-and-how-is-it-performed.html)
- Taxonomía desde humanos, no inventada por el LLM: «Build an error taxonomy from human review instead of asking an LLM to invent one». — [Hamel, Automating Error Analysis](https://hamel.dev/notes/llm/ai-product-engineering/evals-error-analysis.html) (snippet, 2026)
- Arreglar por familia: en un caso real «just three issues accounted for over 60% of all problems»; fallos de fechas «66% of the time», pasaron «from a 33% success rate to 95%»; «The 'tools first' mindset is the most common mistake in AI development»; «Generic metrics are worse than useless»; «Teams with thoughtfully designed data viewers iterate 10x faster». — [Hamel, Field Guide](https://hamel.dev/blog/posts/field-guide/)
- Pass/fail binario con crítica: «a binary pass/fail forces evaluators to make a clear judgment»; criterios como «living documents that evolve alongside their understanding of the problem space». — [Hamel, Field Guide](https://hamel.dev/blog/posts/field-guide/)
- Primero los huecos obvios: «Fix these obvious gaps first before building complex evaluation infrastructure» (FAQ «Should I build automated evaluators for every failure mode I find?»). — [Hamel, Evals FAQ](https://hamel.dev/blog/posts/evals-faq/)
- Anti-sobreajuste del juez: dividir en train/dev/test; «The test set gives you a final check on data that hasn't guided those changes»; tras muchas rondas el evaluador «may do well on the dev set but poorly on new examples». Cifras: ~100 trazas para descubrir errores; juez LLM necesita 100-200 ejemplos etiquetados por modo de fallo; split 10-20 % train / 40-45 % dev / 40-45 % test; 30-50 Pass y 30-50 Fail en dev y test. — [Hamel, How many examples do I need](https://hamel.dev/blog/posts/evals-faq/how-many-examples-do-i-need-for-an-eval.html); [Hamel, Evals FAQ](https://hamel.dev/blog/posts/evals-faq/)
- Métricas de catálogo: «No. Generic evaluations waste time and create false confidence when you use them as quality measures» (pueden servir para «find traces to inspect»). — [Hamel, Evals FAQ](https://hamel.dev/blog/posts/evals-faq/)
- Cuándo repetir: «Re-run error analysis when making significant changes: new features, prompt updates, model switches, or major bug fixes»; «Eval datasets naturally get stale as your product and users change». — [Hamel, Evals FAQ](https://hamel.dev/blog/posts/evals-faq/)
- Juez alineado: «It took three iterations to achieve >90% agreement»; few-shot con críticas «often yields 15-20% higher agreement rates». — [Hamel, Field Guide](https://hamel.dev/blog/posts/field-guide/)
- Shreya Shankar, «criteria drift» (UIST 2024, antiguo pero base del tema): es imposible fijar los criterios antes de ver salidas; incluso quien calificó antes de definir criterios siguió refinándolos y volvió a cambiar notas previas; hacen falta herramientas que permitan iterar criterios e implementaciones a la vez, y eso abre la cuestión de cómo manejar el drift de criterios junto con el drift de modelo o las ediciones de prompt. — [Shankar et al., Who Validates the Validators](https://arxiv.org/abs/2404.12272)
- Eugene Yan (abr-2025): «This cycle—write evals, make changes, run evals, integrate improvements—ensures measurable progress»; «having automated evaluators doesn't remove the need for human oversight»; «If we're not actively reviewing AI outputs and customer feedback, automated evaluators won't save our product»; anti-patrón: «Some folks think that adding another tool, metric, or LLM-as-judge will solve the problems and save the product»; dataset «50:50 split of passes and fails that spans the distribution of inputs». — [Eugene Yan, An LLM-as-Judge won't save the product](https://eugeneyan.com/writing/eval-process/)
- Eugene Yan: empezar con 50-100 casos fallidos y «add organic samples from production» para que el set no sea solo fallos. — [Eugene Yan, Product evals in three simple steps](https://eugeneyan.com/writing/product-evals/) (snippet)
- Jason Liu (ene-2025): «We group queries by topic, user type, complexity, or whatever matters for your business. Then we measure retrieval metrics per segment»; «You won't see that if you never break your dataset into categories»; separar «Inventory means the data simply isn't there» de «Capability means the data is there, but you can't surface it»; ciclo Ship → Log → Discover a failing segment → Add → Train → Collect → Repeat; ejemplo ilustrativo de 70 % de recall global escondiendo segmentos al 5 %; advertencia sobre «80 half-tested solutions layered together». — [Jason Liu, Systematically improving RAG](https://jxnl.co/writing/2025/01/24/systematically-improving-rag-applications/)
- Chip Huyen, «evaluation-driven development»: definir criterios antes de construir; experimentos de prompt con «the same rigor as any ML experiment» (cap. 5). — [O'Reilly, AI Engineering cap. 5](https://www.oreilly.com/library/view/ai-engineering/9781098166298/ch05.html) (snippets de resúmenes; no se leyó el libro)

### Inferences
- La regla operativa de «fix by family» que se desprende: contar fallos por categoría, atacar la categoría más numerosa con un cambio único, y medir en el conjunto apartado. Arreglar caso a caso es exactamente lo que Liu describe como «80 half-tested solutions layered together».
- Las reglas de Hamel contra sobreajuste están pensadas para el *juez* (prompt del evaluador), pero son aplicables al prompt de producción: hill-climb en dev, una sola mirada a test, y re-análisis de errores cuando cambia el prompt.
- «Criteria drift» explica por qué los equipos que afinan contra un test fijo acaban midiendo otra cosa: los criterios cambian al ver salidas nuevas; de ahí la insistencia en refrescar el dataset con muestras orgánicas.

### Gaps
- No se encontró en Eugene Yan ni en Jason Liu una frase literal sobre «overfitting al eval set»; lo más cercano es el refresco con muestras de producción y el enfoque por segmento.
- No se leyó el libro de Chip Huyen; solo resúmenes de terceros.
- No se localizaron citas de Lilian Weng ni de episodios concretos de Latent Space/Lenny con fundadores de CX-AI que traten el bucle post-lanzamiento (las búsquedas devolvieron transcripciones de Hamel/Shankar, no de fundadores de vendors).

---

## 4. ¿Hay evidencia o consenso sobre «congelar el prompt del sistema y cambiar datos» y sobre «cada corrección debe borrar o sustituir, nunca añadir una capa»?

### Takeaway
No hay un estudio que lo formule así, pero hay consenso práctico convergente desde tres lados: los vendors ponen el contenido antes que las instrucciones (Intercom: «Fin always generates answers from your content first»; Ada: conocimiento → acción → coaching), Anthropic desaconseja explícitamente la «laundry list of edge cases» en el prompt, y Hamel/Liu describen la acumulación de parches como anti-patrón. Lo de «borrar o sustituir» aparece como práctica («quita cada instrucción y corre las evals; si no cambia nada, sobra») en blogs secundarios, no en fuente primaria.

### Cited Findings
- Anthropic (sep-2025): «At one extreme, we see engineers hardcoding complex, brittle logic in their prompts to elicit exact agentic behavior», lo cual «creates fragility and increases maintenance complexity over time»; «teams will often stuff a laundry list of edge cases into a prompt. We do not recommend this»; en su lugar «a set of diverse, canonical examples»; «start by testing a minimal prompt with the best model available» y añadir instrucciones «based on failure modes found during initial testing»; «finding the smallest possible set of high-signal tokens that maximize the likelihood of some desired outcome»; «minimal does not necessarily mean short». — [Anthropic, Effective context engineering](https://www.anthropic.com/research/effective-context-engineering-for-ai-agents)
- Intercom: el contenido es la base; guidance solo «to refine or structure those answers further»; «Review your active guidance to ensure you don't have rules that conflict with one another»; «Remove or update conflicting or redundant rules»; si se acerca al límite de 100, «combine related instructions into one piece». — [Intercom, Guidance best practices](https://www.intercom.com/help/en/articles/10560969-fin-guidance-best-practices); [Intercom, Guidance vs Procedures](https://www.intercom.com/help/en/articles/14623785-when-to-use-fin-guidance-vs-procedures)
- Intercom, efecto lateral de reglas globales: una regla global de suscripciones «whenever a customer seems confused» se dispara en medio de un paso de account-lookup; «Audit your global guidance rules for any instructions that could apply broadly across all conversations». — [Intercom, Guidance vs Procedures](https://www.intercom.com/help/en/articles/14623785-when-to-use-fin-guidance-vs-procedures)
- Ada: el coaching cambia comportamiento «without changing its overall logic or retraining the model» y se reserva a «specific changes … based on the unique context of only some conversations»; las instrucciones globales (Custom Instructions) son otra capa. — [Ada, Improvement tactics](https://docs.ada.cx/docs/welcome/improvement-tactics); [Ada, Coaching](https://docs.ada.cx/docs/optimization/coaching)
- Sierra: el conocimiento viaja dentro del snapshot inmutable junto a prompts y modelo, es decir, un cambio de conocimiento es una versión igual que un cambio de código. — [Sierra, ADLC](https://sierra.ai/blog/agent-development-life-cycle) (antiguo)
- Jason Liu: la alternativa a parches es «Discover a failing segment» y añadir extracción/ruteo o entrenar para ese segmento; advierte de «80 half-tested solutions layered together». — [Jason Liu, Systematically improving RAG](https://jxnl.co/writing/2025/01/24/systematically-improving-rag-applications/)
- Breunig (jun-2025), por qué las capas chocan: «Context Clash is when you accrue new information and tools in your context that conflicts with other information»; «Context Confusion is when superfluous content in the context is used by the model to generate a low-quality response»; estudio Microsoft/Salesforce de prompts fragmentados: caída media del 39 %, o3 de 98,1 a 64,1; «when LLMs take a wrong turn in a conversation, they get lost and do not recover». — [Breunig, How long contexts fail](https://www.dbreunig.com/2025/06/22/how-contexts-fail-and-how-to-fix-them.html)
- Blogs secundarios (2026, sin verificar): «prompt debt» = cada bug añade una instrucción y nada se quita «because nobody knows what is load-bearing»; remedio propuesto: quitar cada instrucción una a una y correr la suite; «If the eval scores don't change, the instruction isn't doing anything». — [tianpan, Prompt debt spiral](https://tianpan.co/blog/2026/04/19/prompt-debt-spiral-production-prompts); [insiderllm, Prompt debt](https://insiderllm.com/blog/prompt-debt-system-prompt-maintenance/)

### Inferences
- «Congelar el prompt y cambiar datos» no es una regla publicada, pero es la consecuencia natural de cómo los vendors exponen el producto: CX edita contenido, coaching acotado y procedimientos; el prompt base no está en su UI. Y de la guía de Anthropic: el prompt crece solo con fallos observados en test inicial, y en forma de ejemplos canónicos, no de reglas.
- «Borrar o sustituir, nunca añadir» tiene soporte indirecto fuerte: Intercom exige auditar conflictos y fusionar reglas; Breunig muestra que el coste de una instrucción extra no es cero (clash/confusion); IFScale y ManyIFEval (sección 5) muestran que cada instrucción añadida baja la probabilidad de cumplirlas todas. La prueba de ablación («quítala y mide») es la forma operativa, pero solo la encontré en fuentes secundarias.

### Gaps
- No existe (que haya encontrado) un estudio controlado que compare «corregir vía datos/conocimiento» contra «corregir vía instrucción» en un bot de atención.
- La anécdota de que el equipo de Claude Code recortó su prompt un 80 % para modelos nuevos solo aparece en blogs secundarios; no la cito como hecho.

---

## 5. ¿Qué se sabe de la deriva de prompts y de la relación entre número de instrucciones y calidad?

### Takeaway
Tres benchmarks de 2025 miden lo mismo: la precisión «por instrucción» se mantiene alta, pero la probabilidad de cumplir *todas* las instrucciones de un prompt cae rápido con el número (GPT-4o: 94 % con 1 → 21 % con 10; Claude 3.5 Sonnet: 95 % → 48 %); a escala de cientos de instrucciones (IFScale) hasta los modelos de razonamiento caen a 63-69 % con 500, con sesgo hacia las primeras instrucciones y errores sobre todo por omisión. Hay además sobrecarga de contexto (la memoria de lo cargado se degrada con el tamaño) y los modelos no se recuperan tras un giro erróneo en conversación.

### Cited Findings
- ManyIFEval (sep-2025, 10 LLMs, hasta 10 instrucciones): «performance consistently degrades as the number of instructions increases». Prompt-level accuracy n=1/3/5/10: GPT-4o 0,94/0,73/0,57/0,21; Claude 3.5 Sonnet 0,95/0,88/0,72/0,48; Gemini 1.5 Pro 0,96/0,86/0,71/0,39; o3-mini (high) 1,00/0,95/0,90/0,78. Instruction-level de 1 a 10: GPT-4o 0,94→0,85; Claude 3.5 Sonnet 0,95→0,93; o3-mini 1,00→0,98. Una regresión logística con el número de instrucciones predice el rendimiento «with approximately 10% error, even for unseen instruction combinations»; el estimador ingenuo asume que «The probability of successfully following all n instructions is the product of their individual success probabilities». En código (StyleMBPP) Claude 3.5 Sonnet cae a 0,01 con 6 instrucciones de estilo. — [Harada et al., When Instructions Multiply](https://arxiv.org/html/2509.21051v1)
- IFScale (jul-2025, 20 modelos, hasta 500 instrucciones de inclusión de palabras clave): «even the best frontier models only achieve 68% accuracy at the max density of 500 instructions». Tres patrones: *threshold decay* (gemini-2.5-pro, o3: «maintain near-perfect performance through 150 or more instructions before declining»), *linear decay* (gpt-4.1, claude-3.7-sonnet), *exponential decay* (claude-3.5-haiku, llama-4-scout). Tabla: o3 100/99,6/98,2/97,8/62,8 % a 10/50/100/250/500; gpt-4.1 98,0/98,8/95,4/74,0/48,9 %. Primacía: las instrucciones tardías se violan más, efecto que «peak[s] around 150-200 instructions». «Models overwhelmingly err toward omission errors as instruction density increases». Latencia: o3 de 26,3 s (10 instr.) a 219,6 s (250). — [Jaroslawicz et al., IFScale](https://arxiv.org/html/2507.11538v1)
- WildIFEval (mar-2025, instrucciones reales de usuarios): «all evaluated models experience performance degradation with an increasing number of constraints»; el tipo de restricción importa, no solo el número. — [WildIFEval](https://arxiv.org/html/2503.06573v1) (snippet)
- FollowBench (2024, antiguo): el rendimiento baja del nivel 1 al 5 de restricciones; escalar modelo no lo resuelve por sí solo. — [FollowBench vía resumen de ManyIFEval](https://arxiv.org/html/2509.21051v1) (snippet)
- Anthropic: «as the number of tokens in the context window increases, the model's ability to accurately recall information from that context decreases»; «Context, therefore, must be treated as a finite resource with diminishing marginal returns» («attention budget»). — [Anthropic, Context engineering](https://www.anthropic.com/research/effective-context-engineering-for-ai-agents)
- Breunig, confusión por herramientas: en el Berkeley Function-Calling Leaderboard todos los modelos rinden peor con más de una herramienta; un Llama 3.1 8b cuantizado falla con 46 herramientas y acierta con 19 (arXiv 2411.15399); Databricks: Llama 3.1 405b empieza a degradarse hacia 32k tokens. — [Breunig, How long contexts fail](https://www.dbreunig.com/2025/06/22/how-contexts-fail-and-how-to-fix-them.html)
- Intercom, límite práctico: «Several simple rules work better than one complex rule»; «Complex 'and/or' conditions … make guidance unreliable»; cada regla «should address a single objective». — [Intercom, Guidance best practices](https://www.intercom.com/help/en/articles/10560969-fin-guidance-best-practices)
- Sin verificar: una página resumen cita «Constraint Saturation Evaluation» (arXiv 2608.12426) con colapso pasadas 5-6 restricciones simultáneas; no pude abrir el paper. — [developersdigest](https://www.developersdigest.tech/papers/constraint-saturation-evaluation-instruction-following-collapse) (secundaria, no confirmada)
- Sin verificar: blogs de 2026 hablan de un «acantilado» entre 5 y 15 reglas y de umbral de ~2.500-3.000 tokens de system prompt; no encontré el estudio primario. — [tianpan, Instruction complexity cliff](https://tianpan.co/blog/2026-04-17-instruction-complexity-cliff-llm-compliance) (secundaria)

### Inferences
- La métrica que importa para un bot es la *prompt-level* (todas las reglas a la vez), no la media por regla: con independencia aproximada, 10 reglas al 93 % cada una dan ~48 % de cumplimiento conjunto, que es lo que mide ManyIFEval para Claude 3.5 Sonnet. Cada regla añadida al prompt tiene un coste medible aunque «funcione sola».
- Los modelos de razonamiento (o3, gemini-2.5-pro) aguantan muchas más instrucciones antes del umbral, pero pagan en latencia (×8 en o3 de 10 a 250 instrucciones), lo que choca con los objetivos de p90 de un chat.
- El sesgo de primacía implica que un parche añadido «al final» del prompt es el que menos se cumple.

### Gaps
- No encontré estudios específicos sobre *system prompts largos de atención al cliente* (todos los benchmarks usan tareas sintéticas: palabras clave, formato, estilo de código).
- No hay cifra primaria fiable del «número máximo de instrucciones» para un modelo concreto de 2026; los umbrales de 5-15 reglas provienen de blogs.

---

## 6. ¿Cómo deciden cuándo una corrección va a código (determinista) y cuándo al modelo?

### Takeaway
Regla práctica compartida: todo lo que sea acción con consecuencias (reembolsos, pedidos, cambios de plan), validación de datos, enrutado simple o política dura va a código/herramienta determinista; el modelo decide solo donde hace falta flexibilidad lingüística. Anthropic y OpenAI formulan «empieza por la solución más simple y sube complejidad solo si hace falta»; Sierra exige que la lógica de negocio se aplique «strictly and deterministically».

### Cited Findings
- Anthropic (dic-2024, antiguo): «finding the simplest solution possible, and only increasing complexity when needed»; «Workflows are systems where LLMs and tools are orchestrated through predefined code paths» y «offer predictability and consistency for well-defined tasks»; el enrutado «can be handled accurately, either by an LLM or a more traditional classification model/algorithm»; «You can add programmatic checks» entre pasos; «Actions such as issuing refunds or updating tickets can be handled programmatically». — [Anthropic, Building effective agents](https://www.anthropic.com/research/building-effective-agents)
- Anthropic (sep-2025): las herramientas «should be self-contained, robust to error, and extremely clear with respect to their intended use»; mover cómputo del contexto a la herramienta («offload agentic computation … back into the tool calls themselves»); diseñar argumentos «so that it is harder to make mistakes». — [Anthropic, Writing effective tools](https://www.anthropic.com/engineering/writing-tools-for-agents); [Anthropic, Building effective agents](https://www.anthropic.com/research/building-effective-agents)
- Sierra (antiguo, jul-2024): «deterministic safeguards [must] ensure that your business logic is strictly and deterministically enforced» en momentos como «processing an order or upgrading a plan». — [Sierra, Shipping and scaling](https://sierra.ai/blog/shipping-and-scaling-ai-agents)
- OpenAI, guía práctica (2025): «Building agents requires rethinking how your systems make decisions and handle complexity. Otherwise, a deterministic solution may suffice»; guardrails en capas que combinan clasificadores LLM con «rule-based systems» y la moderation API; intervención humana para «high-risk actions or when agents repeatedly fail». — [OpenAI, A practical guide to building agents](https://cdn.openai.com/business-guides-and-resources/a-practical-guide-to-building-agents.pdf) (el PDF no se pudo extraer como texto; citas vía snippets de búsqueda y resúmenes)
- Intercom: Procedures (flujo estructurado con pasos) frente a Guidance (generación libre), precisamente porque en guidance «steps may be skipped or reordered». — [Intercom, Guidance vs Procedures](https://www.intercom.com/help/en/articles/14623785-when-to-use-fin-guidance-vs-procedures)
- Ada: Actions (API) y Playbooks cuando hay que «collect inputs, apply logic, and trigger Actions»; coaching solo para forma de la respuesta. — [Ada, Improvement tactics](https://docs.ada.cx/docs/welcome/improvement-tactics)
- Hamel, FAQ: primero arreglar lo obvio (a menudo un bug o hueco de datos) antes de construir evaluadores; y re-hacer el análisis de errores tras «prompt updates, model switches, or major bug fixes». — [Hamel, Evals FAQ](https://hamel.dev/blog/posts/evals-faq/)

### Inferences
- Criterio operativo que se desprende: si la regla se puede escribir como condición sobre datos estructurados (importe, estado, fecha, certificación, número de personas), va a código o herramienta; si depende de la interpretación del lenguaje del cliente, va al modelo, pero con la *acción* resultante gestionada por código. Lo que nadie recomienda es duplicar la misma regla en ambos sitios ni «corregir» en el prompt lo que ya es una comprobación de código.
- Los vendors meten en lenguaje natural solo el «qué» (AOP/procedure) y dejan el «cómo» (llamadas, validaciones) en tools; eso evita que CX edite código y que ingeniería edite redacción.

### Gaps
- No encontré una matriz publicada «fallo → código vs modelo» con criterios cuantitativos; todo es cualitativo.
- Hamel tiene una FAQ sobre «guardrails vs evaluators» que no pude leer (la página se cortó antes de la sección de producción).

---

## 7. Anti-patrones documentados (capas de correctores, parches regex, jueces que editan texto, afinar en el test set, etc.)

### Takeaway
Los anti-patrones con fuente son: parchear el prompt con lógica dura y listas de casos límite (Anthropic), reglas globales que se disparan en cualquier contexto y reglas contradictorias (Intercom), añadir un juez o métrica como tirita en vez de arreglar el proceso (Yan), métricas genéricas y «tools first» (Hamel), apilar soluciones a medio probar (Liu), reutilizar el dev set hasta sobreajustar el juez (Hamel), y dejar que un LLM invente la taxonomía de fallos (Hamel). Sobre «jueces que reescriben la salida» y «parches regex» no encontré fuente que los nombre explícitamente.

### Cited Findings
- Lógica dura en el prompt: «hardcoding complex, brittle logic in their prompts … creates fragility and increases maintenance complexity over time»; «stuff a laundry list of edge cases into a prompt. We do not recommend this». — [Anthropic, Context engineering](https://www.anthropic.com/research/effective-context-engineering-for-ai-agents)
- Herramientas infladas: «One of the most common failure modes we see is bloated tool sets that cover too much functionality». — [Anthropic, Context engineering](https://www.anthropic.com/research/effective-context-engineering-for-ai-agents)
- Reglas de guidance mal escritas (lista de Intercom): redacción vaga («Make sure Fin understands our different product types»), varios objetivos en una regla, fragmentos sin verbo, condiciones «and/or» complejas, prohibiciones sin alternativa («pair each 'do not' with a positive instruction»), ofrecer escalado en todo escenario («can lower Fin's resolution rate»), reglas de idioma incondicionales («Always answer in British English» hace que responda en inglés a quien escribe en otro idioma), reglas sobre «si no sabes la respuesta», procesos multi-paso en guidance, lógica multi-turno en guidance, texto dictado en workspaces multilingües (no se traduce). — [Intercom, Guidance best practices](https://www.intercom.com/help/en/articles/10560969-fin-guidance-best-practices)
- Reglas contradictorias: ejemplo de una regla que permite ofrecer un crédito de facturación y otra que exige escalar ante palabras de facturación → «unpredictable behavior». — [Intercom, Guidance best practices](https://www.intercom.com/help/en/articles/10560969-fin-guidance-best-practices)
- Procedimiento que nunca se dispara porque el escalado por defecto tiene precedencia («when a customer asks to speak to an agent»). — [Intercom, Guidance vs Procedures](https://www.intercom.com/help/en/articles/14623785-when-to-use-fin-guidance-vs-procedures)
- Juez como tirita: «Some folks think that adding another tool, metric, or LLM-as-judge will solve the problems and save the product». — [Eugene Yan, eval-process](https://eugeneyan.com/writing/eval-process/)
- Métricas genéricas y herramientas primero: «Generic metrics are worse than useless – they actively impede progress»; «The 'tools first' mindset is the most common mistake». — [Hamel, Field Guide](https://hamel.dev/blog/posts/field-guide/)
- Sobreajuste del juez al dev set: «may do well on the dev set but poorly on new examples»; de ahí el test set intocable; en una diapositiva lista «Overfitting judges to data» como pitfall. — [Hamel, Evals FAQ](https://hamel.dev/blog/posts/evals-faq/); [Hamel, Revenge of the Data Scientist (PDF)](https://hamel.dev/blog/posts/revenge/images/The_Revenge_of_the_Data_Scientist.pdf) (snippet)
- Taxonomía inventada por el LLM: «Build an error taxonomy from human review instead of asking an LLM to invent one». — [Hamel, Automating Error Analysis](https://hamel.dev/notes/llm/ai-product-engineering/evals-error-analysis.html) (snippet)
- Datos sintéticos mal hechos: «Generate user inputs, not outputs» para no heredar los sesgos del generador. — [Hamel, Field Guide](https://hamel.dev/blog/posts/field-guide/)
- Apilar parches: «80 half-tested solutions layered together» (sesgo de intervención). — [Jason Liu, Systematically improving RAG](https://jxnl.co/writing/2025/01/24/systematically-improving-rag-applications/)
- Contexto envenenado: «Context Poisoning is when a hallucination or other error makes it into the context, where it is repeatedly referenced». — [Breunig, How long contexts fail](https://www.dbreunig.com/2025/06/22/how-contexts-fail-and-how-to-fix-them.html)
- Cambios de prompt sin tests: un blog secundario cita un estudio «PromptDebt» (2025, 93.142 ficheros Python) según el cual los cambios de prompt rara vez van acompañados de tests de regresión; no abrí el paper. — [insiderllm, Prompt debt](https://insiderllm.com/blog/prompt-debt-system-prompt-maintenance/) (secundaria, sin verificar)

### Inferences
- «Capas de correctores» (un modelo que corrige a otro, un regex que corrige a ambos) es un caso particular de lo que Anthropic llama lógica dura y frágil y de lo que Breunig llama *context clash*: cada capa añade una fuente de conflicto que nadie puede auditar. La alternativa documentada es un único artefacto por tipo de fallo (conocimiento / procedimiento / herramienta) con test de regresión.
- «Juez que edita texto» no aparece nombrado, pero la línea de Hamel/Yan es clara: el juez evalúa en binario con crítica; si se usa para reescribir, se pierde la medida y se añade una capa más al bucle.

### Gaps
- No encontré fuente primaria que nombre explícitamente «regex patches» ni «judges that edit output» como anti-patrón; lo reporto como inferencia.
- Las cifras de «prompt debt» y los umbrales de tokens provienen de blogs de 2026 sin estudio primario localizado.

---

## Fuentes consultadas (resumen por fecha)

| Fuente | Fecha | Tipo |
|---|---|---|
| Sierra, Agent development life cycle | jun-2024 (antiguo) | vendor |
| Sierra, Shipping and scaling AI agents | jul-2024 (antiguo) | vendor |
| Sierra, Release governance | ago-2026 | vendor |
| Decagon, test-driven | jul-2025 | vendor |
| Decagon, Agent Versioning | nov-2025 | vendor |
| Decagon, Experiment Hub | oct-2026 | vendor (snippet) |
| Intercom, Guidance vs Procedures / Guidance best practices | s/f (2025-2026) | doc de producto |
| Ada, release notes + Improvement tactics | ene-abr-2025 | doc de producto |
| Parloa, Agent Management API | nov-2026 | vendor |
| Anthropic, Building effective agents | dic-2024 (antiguo) | guía |
| Anthropic, Writing tools / Context engineering | sep-2025 | guía |
| OpenAI, Practical guide to building agents | 2025 | guía (PDF no extraíble, vía snippets) |
| Hamel Husain, Evals FAQ / Field Guide | 2025-2026 | practicante |
| Shankar et al., Who Validates the Validators | 2024 (antiguo) | paper |
| Eugene Yan, eval-process | abr-2025 | practicante |
| Jason Liu, Systematically improving RAG | ene-2025 | practicante |
| Breunig, How long contexts fail | jun-2025 | practicante |
| IFScale (arXiv 2507.11538) | jul-2025 | paper |
| ManyIFEval (arXiv 2509.21051) | sep-2025 | paper |
| WildIFEval (arXiv 2503.06573) | mar-2025 | paper (snippet) |
| tianpan / insiderllm (prompt debt) | 2026 | secundaria, sin verificar |
