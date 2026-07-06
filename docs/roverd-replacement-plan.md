# Plan: el "Roverd sudamericano" — plataforma de reservas + pagos nativa-LatAm, lanzada con Diving Planet

Documento de planificación. No implica que el trabajo haya empezado — es la base para alinear alcance antes de escribir código. Ver también `docs/questions_for_owner_business_kb.md` (huecos de negocio pendientes, incluida la pregunta #43 sobre DCC) y `TODO.md` (`Booking Agent` pendiente).

## 0. Próximos pasos — empezar por aquí

En orden de prioridad y dependencia (cada uno bloquea al siguiente):

1. **Números reales de Diving Planet** (bloqueante, hacer primero): volumen de reservas/mes, ticket medio, y cuánto paga realmente hoy en comisión a Roverd. Sin esto no se puede fijar el % objetivo ni hablar con seriedad con proveedores de pago.
2. **Pregunta #44 al owner**: cómo y con qué frecuencia le paga Roverd hoy (¿PayPal? ¿wire?), y si hay algún coste oculto en esa liquidación además del 10%. Referencia mínima a mejorar (ver `docs/questions_for_owner_business_kb.md`).
3. **Contactar a Rapyd/PayU** (prioridad #1) y en paralelo a dLocal/EBANX, siguiendo el checklist de la Fase 0 (§6): resumen de una página, el volumen del paso 1, decidir qué entidad será el "partner", y las 5 preguntas clave — sobre todo si el partner puede ser una empresa colombiana.
4. **Fijar el % de comisión objetivo** de la plataforma con las respuestas anteriores — debe cubrir el coste real del proveedor elegido, dejar margen, y quedar claramente por debajo del 10% de Roverd.
5. **Solo entonces**: crear el repo/servicio nuevo y arrancar la Fase 1 (booking + hold). No antes — construir sin tener resuelto el proveedor de pago es el riesgo de tener que rediseñar el modelo de `Payment` a mitad de camino.

**Lo que NO es un próximo paso todavía**: hablar con otros dive shops/tour operators (eso es después, cuando ya haya algo funcionando con Diving Planet que enseñar) y cualquier parte de UI/panel admin (Fases 3-7), que dependen de que la capa de pagos esté resuelta.

### Mensaje para Andrés (dueño de Diving Planet) — pasos 1 y 2

Resuelve los dos primeros puntos del listado de arriba (números reales + cómo le paga Roverd hoy). Listo para enviar por WhatsApp:

> Hola Andrés! Para seguir avanzando con la idea de mejorar el sistema de pagos y reservas (la posibilidad de bajar la comisión que hoy te cobra Roverd), necesitamos que nos confirmes algunos números y detalles operativos:
>
> 1. Volumen: más o menos, ¿cuántas reservas hacen al mes a través de Roverd? ¿Cuál es el valor promedio de una reserva?
> 2. Comisión real: ¿confirmas que Roverd se queda el 10% de cada reserva pagada online? ¿Hay algún otro costo asociado que hoy no tengamos en cuenta (mensualidad, comisión de retiro, algo así)?
> 3. Cómo te pagan: cuando un cliente extranjero paga online en Roverd, ¿cómo y cada cuánto te llega ese dinero a ti — transferencia bancaria, PayPal, algún otro medio? ¿Es automático o tienes que reclamarlo/revisarlo?
> 4. Ese dinero, ¿te llega directo a tu cuenta en Colombia, o pasa por algún intermediario (PayPal u otra cuenta) antes de llegarte?
> 5. Si tienes a mano, ¿nos compartes un ejemplo (captura o extracto) de cómo se ve esa liquidación cuando te llega?
>
> Con esto podemos avanzar en armar algo que te cueste bastante menos que el 10% actual, y que además te dé control/visibilidad automática de los pagos sin tener que llevar el Excel a mano. ¡Gracias!

## 1. El modelo de negocio real (esto manda sobre todo lo demás)

**El enfoque del proyecto**: construir el equivalente sudamericano de Roverd — una plataforma de reservas + pagos pensada desde el diseño para negocios latinoamericanos (no adaptada a golpes desde un producto centrado en Stripe/EE.UU./Europa como es Roverd hoy). **Diving Planet es el cliente piloto que usamos para construir y validar la plataforma**, no el único destino — el objetivo final es escalar esto a otros dive shops/tour operators de la región (ver "Oportunidad de mercado" más abajo).

**La oferta concreta a Diving Planet (primer cliente, sirve de especificación del MVP)**:
1. **Una sola plataforma para clientes colombianos y extranjeros** — hoy Roverd ni siquiera le da checkout a los clientes colombianos (los manda a un formulario de contacto); nosotros unificamos ambos flujos en el mismo sistema.
2. **Un dashboard/control de pagos que sustituye el Excel manual** (`RESERVAS 2026`) — visibilidad automática de cada reserva, cada pago y su estado, sin transcripción a mano.
3. **El dinero le llega directamente a Diving Planet**, sin un merchant intermediario opaco como es Roverd hoy (que cobra, retiene y liquida después sin que el negocio sepa bien cuándo/cómo) — ver §5 y la comparativa de proveedores para el mecanismo concreto (Rapyd/PayU como candidato principal).
4. **Bajar el 10% de comisión de Roverd** a algo sensiblemente menor, que sea a la vez nuestro ingreso recurrente como plataforma.

Esto último (punto 4) tiene una consecuencia técnica directa: **nos convertimos en una plataforma de pagos tipo marketplace (payment facilitator)**, no solo en un proveedor de software de reservas. Ese matiz cambia la arquitectura de pagos por completo respecto a "integrar Stripe normal en una web", y es el motivo de que la mayor parte de este documento gire en torno a la capa de pagos.

### Oportunidad de mercado: por qué "el Roverd sudamericano" y no solo "una herramienta para Diving Planet"

La investigación de esta misma sesión reveló evidencia concreta de que el hueco no es exclusivo de Diving Planet:

- **Roverd ni siquiera le ofrece checkout a los clientes colombianos**: la web pública redirige a los clientes locales a un formulario de contacto en vez de al widget de pago (ver hallazgo de la prueba en vivo de `divingplanet.org`). El producto está diseñado con Stripe/EE.UU./Europa como eje, y Latinoamérica queda mal servida "de rebote".
- El tramo extranjero sí funciona, pero fuerza una **conciliación manual** en Diving Planet porque el modelo de liquidación de Roverd no está pensado para negocios latinoamericanos (ver §1 más abajo, "Cómo resuelve esto Roverd hoy").
- Esto no es exclusivo de Roverd — la mayoría del software de reservas de este tipo (FareHarbor, Checkfront, Peek, Rezdy...) comparte el mismo sesgo de diseño hacia mercados con Stripe nativo.

**La oportunidad**: una plataforma nativa-LatAm, construida desde el diseño sobre un proveedor de pagos regional (Rapyd/PayU, dLocal o EBANX — ver comparativa en §5) en vez de como parche, podría ofrecerle a cualquier dive shop/tour operator de la región lo que hoy nadie les da bien: checkout real en moneda local con métodos de pago locales (PSE, Nequi, Efecty) para el cliente doméstico, cobro a extranjeros sin la fricción de conciliación manual, y una comisión más baja que el 10% de Roverd.

**El trade-off a tener claro antes de comprometer más esfuerzo**: esto deja de ser "una herramienta a medida para Diving Planet" y pasa a ser una apuesta de producto vertical SaaS real, que necesita validarse con más negocios que solo Diving Planet — el hueco no es una barrera estructural infranqueable, Roverd u otro competidor grande podría cerrarlo simplemente integrando Rapyd/dLocal ellos mismos. La ventaja realista sería llegar primero y con mejor diseño para la región, no una ventaja permanente.

### Cómo se cobra la comisión sin ser nosotros un banco: Stripe Connect

Es el mismo patrón que usan Shopify Payments, Squarespace y el propio Roverd para quedarse su comisión sin necesitar licencia de entidad de pago propia:

1. **Cada negocio (tenant) conecta su propia cuenta** de Stripe mediante un onboarding (Stripe Connect — cuentas tipo *Standard* o *Express*). Diving Planet tiene la suya; un futuro tenant tendría la suya.
2. Cuando un cliente final paga una reserva, se ejecuta un **"destination charge"**: el dinero entra a la cuenta conectada del negocio, y en la misma transacción Stripe descuenta automáticamente un **`application_fee_amount`** que va a nuestra cuenta de plataforma. Ese fee es nuestro % (ej. 3-5%, a decidir — muy por debajo del 10% de Roverd).
3. **Confirmado con el cliente (decisión de negocio ya tomada)**: el riesgo de reembolsos/disputas/chargebacks queda **100% en la cuenta conectada del negocio**, no en la nuestra. Esto es exactamente el comportamiento por defecto de Stripe Connect con cuentas Standard — el negocio conectado es el "merchant of record" legal, nosotros solo somos la plataforma que factura su fee de servicio. Simplifica mucho nuestra exposición legal y operativa.
4. **Quién asume el papel regulado**: Stripe es quien hace KYC/AML de cada negocio conectado y quien está autorizado como procesador de pagos. Nosotros, como plataforma, **no nos convertimos en money transmitter** — ese es el motivo de que este patrón exista.

### Hallazgo confirmado: Colombia NO es país soportado por Stripe — esto rompe el diseño inicial

Verificado directamente en la documentación oficial de Stripe (`stripe.com/global`, `docs.stripe.com/connect/cross-border-payouts`, changelog de Global Payouts 2026-01-28):

- Stripe **no permite que una empresa colombiana abra una cuenta propia**, ni como cuenta de plataforma ni como cuenta conectada de Connect.
- Tampoco es país receptor de los **"cross-border payouts"** (limitados a plataformas/receptores en EE.UU., UK, EEE, Canadá, Suiza) ni de los **15 países nuevos de Global Payouts** añadidos en enero de 2026 (ninguno es Colombia).
- En Latinoamérica, **solo Brasil y México** tienen soporte completo de Stripe.

**Consecuencia**: Diving Planet, como empresa colombiana, no puede ser una cuenta conectada de Stripe Connect tal como planteaba el diseño original de este documento. Hay que elegir entre dos caminos:

**Opción A — Diving Planet constituye una entidad en país soportado** (ej. LLC en EE.UU., ~$100-500/año + cuenta bancaria USD vía Mercury/Wise Business). Esa entidad es quien abre la cuenta Connect y recibe los payouts; Diving Planet se transfiere el dinero a Colombia por fuera de Stripe. Mantiene intacto el modelo original: el riesgo de disputas/chargebacks queda en esa cuenta, no en la nuestra. Requiere que el owner esté dispuesto a montar y mantener esa entidad.

**Opción B — Nosotros somos el Merchant of Record (MoR)**. Nuestra propia cuenta Stripe (registrada en país soportado) procesa todos los cobros directamente; no existe "cuenta conectada de Diving Planet". Le hacemos un payout aparte (Wise Business, wire internacional) restando nuestra comisión. Aquí el riesgo de chargeback recae legalmente en nuestra cuenta, no en la de Diving Planet — hay que compensarlo con una reserva retenida (holdback) por payout o cláusula contractual de repercusión de pérdidas.

**Implicación estratégica para el "kit de fork"**: la mayoría de futuros tenants (otros dive shops/negocios turísticos) también serán empresas latinoamericanas fuera de Brasil/México, y se toparán con el mismo bloqueo. Esto sugiere que **el modelo MoR (Opción B) probablemente deba ser el diseño por defecto de toda la plataforma**, no un parche puntual para Colombia — la Opción A queda como alternativa solo para el tenant que esté dispuesto a montar su propia entidad extranjera.

### Cómo resuelve esto Roverd hoy (evidencia indirecta, no confirmada oficialmente)

Roverd no publica su arquitectura interna de pagos por país, pero la FAQ ya existente en la KB del bot (`faqs.json`: *"tu pago se registra de inmediato en ROVERD, pero el equipo concilia manualmente los pagos poco después"*) encaja exactamente con un modelo **Merchant of Record**: el dinero del cliente entra a la cuenta de Roverd (no a una cuenta propia de Diving Planet, que no puede existir en Colombia), y Roverd le liquida a Diving Planet por una vía separada, probablemente no en tiempo real — de ahí que el owner tenga que conciliar a mano en el Excel `RESERVAS 2026` en vez de ver el dinero aparecer automáticamente. Es decir: **Roverd ya está resolviendo este mismo bloqueo con la Opción B**, y la fricción que hoy sufre el owner (conciliación manual) es previsiblemente un síntoma de ese modelo. Ver pregunta #44 (nueva) en `docs/questions_for_owner_business_kb.md` — pendiente de confirmar con el owner la frecuencia/método/moneda real de esos payouts, dato clave para diseñar algo mejor que lo que ya sufre hoy.

## 2. Qué hace Roverd hoy (línea base a igualar o mejorar)

Confirmado por capturas reales del panel admin de Diving Planet + la web pública de Roverd (roverd.com) + prueba en vivo del checkout público:

| Módulo | Evidencia | Prioridad para el MVP de negocio |
|---|---|---|
| Booking + capacidad con hold temporal | Panel "Booking" + checkout real (cuenta regresiva "09:36 min") | **Crítica — es el prerrequisito técnico para poder cobrar sin sobrevender** |
| Pagos con split de comisión (Stripe Connect) | roverd.com (Stripe/PayPal) + decisión de negocio §1 | **Crítica — es la pieza que genera el ingreso** |
| Reconciliación automática (fin del Excel manual) | Excel `RESERVAS 2026`, columna "Pago" (ROVERD/PADI/CXC) | **Crítica — sin esto no hay confianza del negocio en el sistema** |
| Waivers digitales con workflow de aprobación | Panel "Review Waivers" | Alta — requisito legal, pero no bloquea el modelo de ingreso |
| Notificaciones/recordatorios automáticos | KB (`TODO.md` #40/#42) | Alta, no bloqueante |
| Widget de checkout embebible con branding propio | Captura real del checkout en `divingplanet.org` | Alta — sin esto el negocio no puede vender solo, necesita el panel nuestro |
| Cupones/descuento en checkout | Captura real del checkout | Media |
| Gift cards | Panel, pestaña "Gift Card" | Baja |
| Channel manager / OTAs, portal de agente/revendedor | roverd.com (no visto en uso real) | Baja — confirmar con owner si de verdad lo usa |
| Analítica/dashboard | roverd.com (no visto en uso real) | Baja |

**Antes de construir los módulos de prioridad Baja**, confirmar con el owner si Diving Planet realmente usa channel manager/analítica/gift cards de Roverd o si son funcionalidad del plan que nunca se activó — evita construir lo que el marketing de Roverd promete pero nadie usa.

## 3. Principios de diseño (para que sea forkeable y monetizable por tenant)

1. **Multi-tenant desde el día uno**, porque el modelo de ingresos ES el número de tenants × volumen de cada uno. Diseñar single-tenant y añadir tenants después obliga a reescribir el modelo de datos justo cuando más interesa escalar.
2. **`TenantConfig` incluye el % de comisión de la plataforma** (nuestro `application_fee`) además de moneda(s), métodos de pago, textos legales, branding — es tan variable por tenant como cualquier otro dato de configuración, nunca hardcodeado ni igual para todos (podríamos negociar % distintos por volumen, igual que Roverd tiene plan Standard vs. Enterprise).
3. **El core de reservas + pagos es un servicio independiente del chatbot.** El bot de WhatsApp es un cliente más de esa API, igual que mañana lo sería un widget web embebido o el panel admin de cada negocio. Así se reutiliza el core en otro negocio sin arrastrar lógica de Chatwoot/WhatsApp de Diving Planet.
4. **Reutilizar el stack ya validado en este repo**: FastAPI + SQLAlchemy/asyncpg + Alembic + Postgres + Redis + Docker Compose + Caddy sobre Hetzner. Mismo equipo, mismo patrón de despliegue, sin motivo técnico para cambiar de stack.
5. **Migración incremental, nunca "big bang"**: convivencia con Roverd en paralelo (dual-run) hasta validar en producción real con dinero y buceadores reales de por medio.

## 4. Arquitectura propuesta (visión de alto nivel)

```
                     ┌─────────────────────┐
                     │   Bot WhatsApp/Web   │  (repo actual)
                     └──────────┬───────────┘
                                │ API interna (REST)
                     ┌──────────▼───────────┐
                     │  Booking Platform API │  ← nuevo servicio
                     │  (FastAPI, multi-tenant)
                     └───┬────┬────┬────┬────┘
                         │    │    │    │
                 ┌───────▼┐ ┌─▼──────────▼┐ ┌▼──────────┐
                 │Bookings│ │  Payments    │ │Notificac. │
                 │+Capacity│ │ (Stripe      │ │ (email/SMS)│
                 │ +Hold   │ │  Connect)    │ └───────────┘
                 └────────┘ └──────┬───────┘
                                   │ application_fee_amount
                                   ▼
                         ┌───────────────────┐
                         │ Nuestra cuenta     │  ← ingreso real del negocio
                         │ plataforma Stripe  │
                         └───────────────────┘
                         │
                 ┌───────▼────────┐
                 │ Postgres (multi-│
                 │ tenant, tenant_id│
                 │ FK en todo)      │
                 └─────────────────┘

    Consumidores adicionales futuros: panel admin por tenant, widget de reserva
    público embebible, apps de otros tenants (fork).
```

### Entidades de dominio (borrador)

- `Tenant` (negocio: Diving Planet, y futuros forks) — incluye `stripe_connected_account_id` y `application_fee_percent`.
- `TenantConfig` (moneda(s), idiomas, métodos de pago, % anticipo, textos legales, branding del widget).
- `Resource` (instructor, bote, set de equipo — lo que limita capacidad).
- `Activity` / `Service` (equivalente a `services.json` actual, pero vivo en DB).
- `Session` / `Schedule` (instancia de una actividad en fecha/hora con recursos asignados y cupo).
- `Booking` (reserva: cliente, sesión(es), cantidad, precio total, balance pendiente, **estado `holding` con expiración antes de `confirmed`**).
- `Payment` (transacción: proveedor, monto, moneda, estado, referencia externa, **`application_fee_amount` cobrado**, `promo_code` aplicado).
- `Waiver` (documento firmado, estado de aprobación, ligado a booking) — Fase posterior.
- `Customer` (datos del buceador: certificación, talla equipo, último buceo — hoy vive solo en el Excel).
- `GiftCard` — Fase posterior.

## 5. Estrategia de pagos (el corazón del proyecto)

- **Internacional (USD, tarjeta)**: Stripe Connect, cuentas conectadas tipo Standard, `destination charge` + `application_fee_amount`. Es la vía a construir primero — mercado más maduro, menor incertidumbre regulatoria.
- **Colombiano (COP, Llave/Bancolombia/ACH, 50% del pago hoy)**: pendiente de investigar en Fase 0 de pagos si Wompi/ePayco/PayU soportan un modelo de marketplace equivalente. Si no, alternativas a evaluar: (a) arrancar monetizando solo el tramo USD y dejar el COP con el flujo actual (Roverd o manual) hasta resolver esto, o (b) un modelo de payout manual/programado con revisión legal previa (nos acerca más a ser money transmitter de facto — no decidir sin abogado local).
- **Bloqueo confirmado — Colombia no es país Stripe**: independientemente del tramo COP, ni siquiera el tramo USD puede montarse con Diving Planet como cuenta conectada propia, porque Stripe no admite empresas colombianas (ver detalle y opciones A/B en §1). Hay que decidir entre que Diving Planet monte una entidad en país soportado (Opción A) o que nosotros seamos el Merchant of Record (Opción B) antes de diseñar el `Payment` de la Fase 2.
- **DCC (conversión de moneda dinámica)**: se confirmó en el checkout real de Roverd que el propio gateway convierte a la divisa local del cliente con su propio tipo de cambio (ver `docs/questions_for_owner_business_kb.md` #43). Para nuestra plataforma, cobrar siempre en USD nativo (sin DCC) o ser transparentes sobre el tipo de cambio aplicado es una ventaja competitiva concreta y diferenciadora frente a Roverd, no solo paridad.
- **Reserva con hold temporal**: el checkout real de Roverd bloquea el cupo con cuenta regresiva mientras se completa el pago. Nuestro `Booking` necesita un estado `holding` con TTL (natural en Redis, ya usado en este repo vía `state_store.py`) antes de pasar a `confirmed` — sin esto, dos clientes pueden ver el mismo cupo libre a la vez y hay sobreventa real con dinero de por medio.
- **Cupones/promo codes**: el checkout real de Roverd los soporta; el modelo de `Payment` debe contemplarlo desde el diseño.
- **Fin de la conciliación manual**: hoy el owner transcribe a mano cada reserva al Excel `RESERVAS 2026` (columna "Pago": ROVERD/PADI/CXC). Con webhooks de Stripe actualizando `Payment` en tiempo real, el manifiesto diario (certificación, talla BCD, hotel, país, estado de pago) debería generarse solo desde `Booking`+`Customer`+`Payment` — cero transcripción manual es el criterio de éxito de la Fase 2.

### Cuánto se queda Stripe realmente (coste, no nuestro margen)

Números reales para una actividad de **100 € / cuenta base en la UE** (asumiendo que la cuenta de plataforma se registra en Europa, hipótesis razonable dado que Colombia no es viable — ver más abajo la variante en USD/EE.UU.):

| Caso | Fórmula Stripe | Fee | % efectivo | Neto sobre 100 € |
|---|---|---|---|---|
| Tarjeta europea (EEE), sin conversión | 1.5% + 0.25€ | 1.75 € | 1.75% | 98.25 € |
| Tarjeta UK, sin conversión | 2.5% + 0.25€ | 2.75 € | 2.75% | 97.25 € |
| Tarjeta UK, con conversión de moneda | 2.5% + 0.25€ + 2% | 4.75 € | 4.75% | 95.25 € |
| Tarjeta internacional (EE.UU./resto), sin conversión | 3.25% + 0.25€ | 3.50 € | 3.50% | 96.50 € |
| Tarjeta internacional, con conversión de moneda | 3.25% + 0.25€ + 2% | 5.50 € | 5.50% | 94.50 € |

Dado el perfil real de clientes de Diving Planet (mayoría EE.UU./Europa pagando en USD, no en EUR), el escenario más representativo es el de **cuenta Stripe en EE.UU. cobrando siempre en USD** (evita el recargo de conversión ofreciendo una sola moneda de asentamiento):

| Caso | Fórmula Stripe (cuenta US) | Fee | Neto sobre $100 |
|---|---|---|---|
| Cliente con tarjeta emitida en EE.UU. (doméstica) | 2.9% + $0.30 | $3.20 | $96.80 |
| Cliente con tarjeta internacional (Europa/otros), cobrando siempre en USD | 2.9% + 1.5% + $0.30 | $4.70 | $95.30 |
| Cliente internacional + conversión de moneda (evitable) | 2.9% + 1.5% + 1% + $0.30 | $5.70 | $94.30 |

**Conclusión de margen**: el coste real de Stripe para el perfil de Diving Planet ronda **3.2%-4.7%**, no el "2.9% de anuncio". Con destination charges, este coste se descuenta por defecto de nuestro `application_fee` (salvo que se configure `on_behalf_of` para que lo absorba la cuenta conectada) — nuestra comisión objetivo debe fijarse por encima de ese suelo real, no del número de marketing, para tener margen positivo genuino frente al 10% de Roverd.

### Comparativa de proveedores de pago (alternativas a Stripe para el problema de Colombia)

| Opción | ¿Colombia como merchant propio? | Split/marketplace nativo | Tarjetas internacionales | Quién asume riesgo de chargeback | Madurez/confianza | Pricing | Contras principales |
|---|---|---|---|---|---|---|---|
| **Stripe + Opción A** (LLC extranjera de Diving Planet) | No directamente — vía entidad puente en EE.UU./UE | Sí (Connect nativo, el mejor documentado del mercado) | Excelente | El tenant (vía su LLC) | Máxima — estándar de facto | Público, transparente (2.9%+$0.30, +1.5% intl, +1% conversión) | Depende de que el owner monte y mantenga una entidad extranjera — fricción real |
| **Stripe + Opción B** (nosotros como MoR) | No aplica — nosotros procesamos todo | Sí, pero simulado internamente (no es Connect real) | Excelente | **Nosotros** | Máxima en tecnología, riesgo lo cargamos nosotros | Igual que arriba | Nos volvemos responsables legales de cada chargeback de cada tenant — no escala con muchos tenants de distinto riesgo |
| **dLocal** | **Sí** — pensado para esto | Sí (`Platforms`: User + Liable accounts, reparto por %) | Sí, nativo (tarjetas + PSE/Nequi/Efecty/Bre-B) | El sub-merchant (Diving Planet), como Stripe Connect | Alta — usado por Amazon/Uber/Booking en emergentes | Sin self-service público, requiere cotización | Onboarding más lento/manual (KYC vía ejecutivo comercial) |
| **EBANX** | **Sí** — MoR nativo por diseño | Sí (split hacia "vendors", payouts individuales/lote) | Sí, trata todo como transacción doméstica | Depende del modelo elegido con ellos | Alta — comparable a dLocal, fuerte en LatAm | Sin self-service público, cotización | Mismo problema de onboarding comercial que dLocal |
| **PayU LatAm / Rapyd** (ver estudio detallado abajo) | **Sí** — nace en Colombia, requisitos simples (NIT) | Sí, vía producto de marketplace de **Rapyd** (wallets + split + escrow) | Sí | El sub-merchant/wallet (Diving Planet) | Alta localmente; controlada por Rapyd desde marzo 2025 | **Mixto**: tarifa de aceptación estándar es pública (3.49%+800 COP); el producto de marketplace/split requiere cotización comercial | Marca en transición (PayU→Rapyd); sin confirmar si el "partner"/plataforma también necesita ser entidad extranjera |
| **Mercado Pago** | Sí | Sí (`marketplace_fee` en su API) | Sí, aunque más débil fuera de LatAm | El sub-vendedor | Alta confianza del usuario final | Público parcialmente | Menos especializado en tráfico internacional (fuerte LatAm-a-LatAm, no turista USD) |
| **Wompi / ePayco** | Sí (nativas colombianas) | No encontrado modelo de marketplace maduro | Limitado — enfocadas en pago doméstico COP | El propio negocio | Alta en Colombia, nula fuera | Público, tarifas locales bajas | No resuelven el problema de cobrar % automáticamente; solo sirven para el tramo 100% doméstico |
| **Adyen** | Incierto — "acepta pagos en Colombia" no confirma cuenta de plataforma colombiana | Sí (`Adyen for Platforms`), cobertura Colombia sin confirmar | Excelente | Depende de configuración | Máxima (enterprise) | Solo enterprise, sin autoservicio | Probablemente sobredimensionado/caro para el volumen inicial |

**Por qué algunas filas dicen "requiere cotización" y otras "público"**: hay dos productos distintos en cada proveedor. (1) Aceptar pagos como comercio normal — esto siempre tiene tarifa pública y alta autoservicio (rellenas un formulario, sin hablar con nadie). (2) El producto de **marketplace/split payments** (la pieza que nos deja cobrar nuestra comisión automáticamente entre varios negocios) — este SÍ requiere hablar con el equipo comercial de cada proveedor para un contrato a medida, porque el precio depende de volumen esperado, número de sub-merchants, y reparto de riesgo. Esto aplica igual en Stripe Connect Enterprise, dLocal, EBANX y PayU/Rapyd — no es que oculten precio por capricho, es como se vende este tipo de producto en toda la industria.

### Estudio en profundidad: PayU LatAm / Rapyd

**Hallazgo crítico de ownership**: Rapyd completó la adquisición de PayU GPO (Global Payment Organisation) en Latinoamérica y África en **marzo de 2025** (~$610M). Confirmado directamente: `corporate.payu.com/colombia/` y `colombia.payu.com/tarifas/` **redirigen automáticamente a rapyd.net**. La marca "PayU" sigue de cara al comercio colombiano, pero la entidad real detrás — contrato, KYC, soporte, roadmap — es ahora Rapyd. Cualquier negociación futura debe dirigirse a Rapyd como la empresa real, no asumir que "PayU" es independiente.

**Requisitos de afiliación en Colombia**:
- Persona jurídica (caso Diving Planet): negocio registrado ante la DIAN, con NIT.
- Persona natural: mayor de 18, cédula, cuenta bancaria local.
- Apertura de cuenta: gratis.

**Tarifas confirmadas (aceptación estándar, pública)**:

| Concepto | Tarifa |
|---|---|
| Tarjetas crédito/débito + PSE | 3.49% + 800 COP por transacción |
| Costo administrativo mensual | $127.700 COP + IVA — solo se activa con +6 meses sin vender Y +12 meses de antigüedad (no penaliza uso normal) |
| Retiros a cuenta bancaria | 3 gratis/mes; desde el 4º, 6.500 COP + IVA |

Comparado con el 10% de Roverd, el 3.49%+800 COP deja mucho margen para añadir nuestra comisión de plataforma encima y seguir muy por debajo del 10%.

**Producto de marketplace (ahora bajo Rapyd, no "PayU" clásico)**:
- Confirmado: Rapyd ofrece **wallets jerárquicos** — un "client wallet" (nosotros, la plataforma) + **wallets de sub-merchant** por cada negocio (Diving Planet, futuros tenants).
- **Split payments automático** entre wallets, con opción de retener fondos en **escrow**.
- **Onboarding de sub-merchants vía "Partner Portal"**: nosotros como partner, cada negocio se registra vinculado a nuestra cuenta — el patrón de marketplace que necesitamos.
- Confirmado explícitamente: Rapyd ofrece adquirencia de tarjeta local en Colombia **y** servicios de Merchant of Record para comercios internacionales — cubre tanto el escenario "Diving Planet como sub-merchant real" como un eventual escenario MoR para otro tenant.
- El "Split Settlements" con "child merchants" que documenta PayU es específicamente de **PayU India** — no confirmado que sea el mismo producto exacto en LatAm; lo relevante en LatAm es el producto de marketplace de Rapyd descrito arriba.

**Sin confirmar todavía (no investigable por web, requiere hablar con ventas)**:
- El % de fee específico del producto de marketplace/split (la tarifa de 3.49%+800 COP es solo la de aceptación estándar).
- Si el "client wallet"/partner (nosotros, la plataforma) también necesita ser una entidad de un país concreto, o si puede ser una empresa colombiana — este es el riesgo #1 a validar antes de comprometernos, porque si hay la misma restricción de país que con Stripe, volvemos al mismo problema.
- Tiempos reales de liquidación/settlement al sub-merchant.

**Valoración**: hasta ahora, la opción que mejor resuelve el problema completo — tarifa base pública y razonable, alta simple para empresa colombiana ya constituida, y un producto de marketplace real. Siguiente paso concreto: contactar a Rapyd/PayU Colombia para cotizar el producto de marketplace y confirmar el requisito de país del partner.

## 6. Fases

### Fase 0 — Discovery y validación del modelo de negocio (sin código)
- **Pagos — decisión bloqueante**: elegir Opción A (Diving Planet constituye entidad en país soportado por Stripe) vs. Opción B (nosotros como Merchant of Record) vs. **Opción C (proveedor LatAm nativo — PayU/Rapyd, dLocal o EBANX como marketplace, Diving Planet como sub-merchant real)** — ver §1 y §5. Confirmar con el owner cómo/con qué frecuencia le paga Roverd hoy (pregunta #44 de `docs/questions_for_owner_business_kb.md`) como referencia de mínimo aceptable.
- **Contactar a Rapyd/PayU Colombia** (candidato principal, ver estudio en §5): cotizar el producto de marketplace/split y confirmar si el "partner"/plataforma puede ser una empresa colombiana o necesita también una entidad extranjera. En paralelo, pedir cotización equivalente a dLocal y EBANX como comparación.

  **Checklist para preparar el contacto (antes de escribirles)**:
  - [ ] Resumen de una página: qué es la plataforma (booking + pagos para dive shops/tour operators, modelo marketplace), quién es el primer cliente real (Diving Planet), y qué producto se necesita específicamente (marketplace/split payments, no aceptación estándar).
  - [ ] Volumen real estimado (reservas/mes y ticket medio de Diving Planet) — piden esto en el primer contacto, sin esto la conversación queda coja.
  - [ ] Decidir qué entidad legal será el "partner"/plataforma de cara al proveedor (¿existe ya y en qué país?) — es la pregunta que todos van a hacer primero.
  - [ ] Canal correcto por proveedor, no soporte genérico:
    - Rapyd: formulario de contacto comercial / sección "Marketplaces" en rapyd.net — mencionar explícitamente su producto de "Platforms" y Colombia.
    - dLocal: página "dLocal for Platforms" (formulario de demo/contacto) — mencionar "split payments" y Colombia.
    - EBANX: contacto comercial en business.ebanx.com — mencionar su modelo de Merchant of Record y split hacia vendors.
  - [ ] Guion de preguntas para la primera llamada:
    1. ¿El partner/plataforma puede ser una empresa colombiana, o necesita estar en otro país?
    2. ¿Cuál es la tarifa específica del producto de marketplace/split (no la de aceptación estándar)?
    3. ¿Cómo es el proceso de KYC/onboarding de cada sub-merchant y cuánto tarda?
    4. ¿Con qué frecuencia se liquida al sub-merchant?
    5. ¿Hay volumen mínimo para acceder a este producto, o vale para un negocio del tamaño de Diving Planet?
- **Pagos**: confirmar si Wompi/ePayco tienen equivalente de marketplace/split para el tramo estrictamente doméstico COP; si no, queda solo como complemento, no como sustituto de la capa de comisión.
- **Números**: volumen real de reservas/mes de Diving Planet y comisión actual pagada a Roverd (10%) → caso de negocio cuantificado, y punto de partida para fijar nuestro % objetivo.
- **Legal**: implicaciones de operar como plataforma de pagos con Stripe Connect en Colombia/internacional; requisitos legales del waiver digital.
- Confirmar con el owner qué módulos de Roverd (channel manager, analítica, gift cards) usa de verdad hoy.
- **Validación de mercado (nuevo)**: hablar con 2-3 dive shops/tour operators más en Colombia (o LatAm) para confirmar si sufren el mismo problema que Diving Planet con Roverd (checkout inexistente para clientes locales, conciliación manual, 10% de comisión) — antes de invertir en construir el "kit de fork" (Fase 7), confirmar que hay demanda real más allá de un solo cliente. Ver §1 "Oportunidad de mercado".
- Entregable: caso de negocio cuantificado + decisión de proveedor(es) de pago + señal de validación de mercado, antes de tocar código.

### Fase 1 — Core de reservas + capacidad con hold
- Modelo de datos: `Tenant`, `Resource`, `Activity`, `Session`, `Booking` con estado `holding`→`confirmed`/`expired`.
- API REST (FastAPI): disponibilidad, crear hold, confirmar/cancelar.
- Migrar `services.json` de estático a datos vivos en DB.
- El bot sigue enlazando a Roverd para el pago final en esta fase (dual-run) — solo disponibilidad y hold migran.
- Tests de concurrencia: dos holds simultáneos sobre el mismo cupo no deben ambos tener éxito (el bug más caro de no cubrir bien, ahora con dinero real de por medio en la Fase 2).

### Fase 2 — Pagos con Stripe Connect y comisión de plataforma
- Onboarding de Diving Planet como cuenta conectada Stripe (Standard).
- `destination charge` + `application_fee_amount` en cada `Payment` — este es el primer euro/dólar de ingreso real del proyecto.
- Webhooks de Stripe actualizando `Payment`/`Booking` sin intervención manual.
- Sustituye el `booking_url` de Roverd para el tramo internacional (USD).
- Tramo colombiano: según lo decidido en Fase 0 — puede quedar para una Fase 2b separada si no hay proveedor de marketplace maduro para COP.
- Criterio de salida de fase: 0 reservas del tramo cubierto requieren transcripción manual al Excel.

### Fase 3 — Widget de checkout embebible
- Componente embebible (branding por tenant) equivalente al modal real de Roverd: Fecha → Información → Check-Out, con cuenta regresiva de hold y campo de cupón.
- Es lo que permite a un negocio vender sin depender de nuestro panel ni del bot.

### Fase 4 — Waivers digitales
- Firma digital ligada a `Booking`, workflow pending→approved/declined igual al de Roverd.
- Envío automático al confirmar reserva.

### Fase 5 — Panel admin por tenant
- Vistas equivalentes a las capturas actuales: bookings con balance, calendario con capacidad, revisión de waivers.
- Roles (Owner/Staff) con permisos distintos.

### Fase 6 — Notificaciones automáticas
- Recordatorios pre-actividad + confirmaciones de reserva/pago, reutilizable por cualquier tenant.

### Fase 7 — Kit de fork (multi-tenancy comercial)
- Documentar el proceso de alta de un nuevo tenant: onboarding Stripe Connect, variables de `TenantConfig`, checklist de puesta en marcha — es el entregable que convierte esto en un producto vendible a otros negocios, no solo una solución a medida para Diving Planet.
- Validar con un segundo tenant (piloto) antes de vender el fork de verdad.

### Fase 8 — Avanzado (solo si Fase 0 confirma uso real)
- Gift cards, channel manager/OTAs, dashboard de analítica, portal de agente/revendedor.

### Fase 9 — Migración y corte final de Roverd
- Checklist de corte: cancelar plan de Roverd, confirmar que ningún link viejo (`book.divingplanet.org/...`) siga circulando en KB/mensajes del bot.

## 7. Riesgos y consideraciones transversales

- **Sobreventa de cupo (overbooking)**: mitigado por el diseño de hold con TTL (Fase 1) — ahora con dinero real circulando, no es negociable.
- **Regulatorio de pagos**: Colombia no es país soportado por Stripe (confirmado, §1) — Diving Planet no puede ser cuenta conectada propia. Con Opción A (entidad extranjera del tenant) se mantiene el modelo original (riesgo 100% en la cuenta conectada); con Opción B (nosotros como Merchant of Record) el riesgo de disputas pasa a nuestra cuenta y hay que mitigarlo con reservas retenidas o cláusula contractual de repercusión. El tramo COP sigue siendo una incógnita adicional a resolver en Fase 0 con asesoría legal.
- **Riesgo de disputas/chargebacks**: la decisión de que recaiga 100% en la cuenta del tenant solo es posible bajo la Opción A. Si el Fase 0 concluye que la mayoría de tenants (Diving Planet incluido) no van a montar una entidad extranjera propia, hay que asumir Opción B como diseño por defecto y presupuestar ese riesgo (holdback por payout, reserva de contingencia) en vez de asumir que siempre será cero para nosotros.
- **Cumplimiento PCI**: no tocar datos de tarjeta directamente — usar Stripe Elements (hosted fields tokenizados), igual que ya hace Roverd hoy según la prueba en vivo del checkout.
- **Validez legal del waiver digital** en Colombia — confirmar antes de asumir que una firma en pantalla basta (no bloquea el modelo de ingreso, pero sí la Fase 4).
- **Continuidad operativa durante la migración**: Diving Planet opera con buceadores reales todos los días; cualquier corte debe ser progresivo y reversible.
- **Alcance vs. marketing de Roverd**: no todo lo que roverd.com promete está en uso real por el cliente — verificar antes de invertir esfuerzo en Fase 8.
- **Relación con el chatbot actual**: `booking_agent.py` es hoy un stub — este proyecto lo reemplaza por una integración real contra la nueva API.

## 8. Hallazgos del checkout real (captura en vivo, curso Open Water)

Prueba en vivo del flujo de "Reservar" en `divingplanet.org/curso-padi-cartagena/basico-open-water/` hasta la pantalla de pago:

1. **Widget embebido (overlay/modal)**, no redirección de página completa — branding blanco propio de Diving Planet. El sustituto necesita un componente embebible equivalente (Fase 3), con el branding resuelto vía `TenantConfig`.
2. **Flujo en 3 pasos**: Fecha → Información → Check-Out, dentro del mismo modal.
3. **Hold de cupo con cuenta regresiva** ("Le quedan 09:36 minutos para asegurar su reserva") — confirma el diseño de `Booking.holding` con TTL de la Fase 1.
4. **DCC en el propio checkout**: 693.00 USD mostrado como "Pagar 606.89 EUR" (tipo de cambio 0.876 visible) — la conversión la hace el gateway, no "el banco después" como dice hoy la FAQ del bot. Ver pregunta #43 en `docs/questions_for_owner_business_kb.md`, pendiente de confirmar con el owner antes de tocar `faqs.json`. Oportunidad competitiva: ofrecer cobro nativo en USD sin margen de DCC.
5. **Campo de código de descuento** en el checkout — soporte de cupones a incluir en el modelo de `Payment` (Fase 2/3).
6. **Resumen titulado "Wallet Overview"** — sugiere que Roverd modela el checkout como carrito de sesión, posiblemente multi-actividad por pago; revisar si debe mapear 1:1 con el carrito mixto que ya maneja el bot (`decision_tree.py`, `mixed_cart_*`).
7. **Campo de tarjeta tokenizado** (hosted field, botón "Utilizar" separado) — confirma que Roverd no toca el PAN directamente; replicar con Stripe Elements para no ampliar alcance PCI-DSS propio.

---

Ver §0 al principio del documento para los próximos pasos priorizados.
