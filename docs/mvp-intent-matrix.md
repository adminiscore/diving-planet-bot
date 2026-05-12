# MVP intent matrix

This matrix defines the commercial-operational scope for the first robust MVP: inform, qualify, recommend, and prepare conversion through a human advisor when needed.

## Decision rule

- Use the decision tree for high-volume guided paths and qualification.
- Use RAG for controlled FAQs and factual details from the curated knowledge base.
- Escalate to a human for booking intent, real availability, payments, medical/safety questions, complaints, custom logistics, low confidence, or special requests.

## Matrix

| Intent | User examples | Qualification questions | Base recommendation / response | Main route | Conversion data to capture | Escalation trigger | Current repo status | Next step |
|---|---|---|---|---|---|---|---|---|
| Ambiguous first contact | "Hola, quiero información" / "What do you offer?" | Language, desired activity, experience level, location | Ask one clear question to classify: certified diver, first time, course, snorkel, prices, booking | Tree first, RAG for free text | Language, broad intent | User asks to book or gives complex free text | Covered by welcome/main menu and early free-text routing | Refine first-contact copy around recommendation |
| Dive baptism / minicourse | "Es mi primera vez buceando" / "I want to try diving" | Date, people, swimming comfort, age/minors, Cartagena vs islands | Recommend minicourse / Discover Scuba because no certification is needed | Tree | Service, date, people, ages if minors, location, language | Medical condition, minors/special case, booking intent | Strong coverage in decision tree and FAQs | Add lead-capture step later |
| Certified fun dives | "Soy buzo certificado" / "I want 2 dives" | Certification, last dive, number of dives, date, people, location | Recommend 2 dives / 1 day or multi-day package depending on interest | Tree | Certification status, last dive, selected package, date, people, location | 2+ years inactive with special case, 500+ dives, booking intent | Strong coverage for 2/5/7/9 packages | Add structured lead summary |
| Mixed group | "Somos buzos y otros quieren snorkel" | Group composition, certified count, beginner count, snorkelers, date, location | Explain they can travel together while each subgroup does the right activity | Tree + human | Group breakdown, date, service mix, location, language | Always escalate for pricing/logistics confirmation | Basic coverage; marked for polishing | Improve mixed-group branch and advisor summary |
| Snorkel / companions | "Solo quiero snorkel" / "Can I join without diving?" | People, age/children, swimming comfort, Cartagena vs islands | Recommend snorkeling tour for surface activity and companions | Tree + RAG FAQs | Service, date, people, ages if minors, location | Children/special needs, booking intent | Good beginner/snorkel tree coverage | Add food/photos/logistics FAQs |
| Open Water course | "Quiero sacarme el Open Water" | Prior experience, available days, origin, dates, age, language | Explain certification path and time commitment | Tree + RAG | Course, dates, available days, origin, age, language | Wants exact scheduling/availability/payment | Partial tree and service coverage | Add course requirements KB details |
| Advanced / Rescue / Divemaster | "Quiero hacer Advanced" / "Do you offer Rescue?" | Current certification, dates, goals, available days | Explain course at high level and pass to advisor for planning | Tree + human | Course interest, current certification, dates, language | Most course planning should escalate | Basic service entries only | Add detailed course requirement docs |
| Prices and discounts | "Cuánto cuesta?" / "Do Colombians get discount?" | Service, nationality/residency, Cartagena vs islands, group size | Give official price only if present; otherwise explain advisor/web confirmation | Tree + RAG | Service, nationality, group size, location | Undefined price, custom quote, discount combination | Weak: many prices are `precio_a_definir` | Confirm and update pricing source of truth |
| Availability / booking | "Hay cupo mañana?" / "I want to book" | Date, service, people, language, location | Do not confirm availability; collect basics and hand off | Tree + human | Date, service, people, name if appropriate, location, language | Always escalate for real availability or booking | Booking cutoff exists; no real availability integration | Add lead summary and Chatwoot handoff flow |
| Medical / safety question | "Tengo asma" / "Estoy embarazada" | Minimal context only; avoid diagnosis | State staff must review the specific case | Human | Topic summary, service interest, language | Always escalate | Covered by sensitive escalation rules | Keep strict; add more medical test cases later |
| Cancellation / change | "Quiero cancelar" / "Can I change my date?" | Existing booking date, service, issue summary | Avoid resolving directly; refer to policy and human support | RAG + human | Booking reference summary if safely provided, date, issue | Existing booking, refund/change request | Partial policy coverage | Add structured cancellation/change KB |
| Hotels / island pickup / transfers | "Estoy en Cocoliso" / "Me recogen en mi hotel?" | Island, hotel, maritime access, date, service | Explain pickup if maritime access and pricing differs from Cartagena | Tree + RAG + human | Island, hotel, service, date, people | Non-standard hotel, no dock, complex logistics | Partial island/hotel selector and policy | Add hotel/island logistics KB |
| Food / allergies | "Qué incluye el almuerzo?" / "Soy alérgico" | Allergy type, service, date | Confirm lunch is included where applicable; do not promise special menu unless confirmed | RAG + human | Allergy note, service, date | Allergy or dietary restriction | Weak: only lunch inclusion exists | Add food/menu/allergy policy |
| Photos / videos | "Incluye fotos?" / "Can I get videos?" | Service, date, whether already booked | Explain photos/videos are not included if that remains policy; ask advisor for options | RAG + human if purchase/detail | Service, date, media request | Pricing/delivery/after-service request | Partial: not included in FAQ | Add dedicated media FAQ/policy |
| Talk to advisor | "Quiero hablar con alguien" | None beyond language/context already known | Transfer politely and keep summary context | Human | Current intent, selected service, language, known details | Explicit request | Covered by escalation keywords/tree | Implement stronger structured summary later |

## MVP priorities

1. Keep the main tree focused on qualification and recommendation.
2. Keep RAG limited to clean, factual FAQs.
3. Escalate whenever the answer depends on live availability, payments, medical/safety evaluation, or custom logistics.
4. Add structured lead summaries before adding complex booking automation.
