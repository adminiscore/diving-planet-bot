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
> 6. Por otro lado, ¿nos puedes pasar el texto del waiver/descargo de responsabilidad que usan hoy (el que se firma en Roverd antes de bucear)? Así no partimos de cero al diseñar esa parte.
>
> Con esto podemos avanzar en armar algo que te cueste bastante menos que el 10% actual, y que además te dé control/visibilidad automática de los pagos sin tener que llevar el Excel a mano. ¡Gracias!

### Huecos abiertos — no técnicos, pero bloquean si no se resuelven

No son parte del análisis de pagos/arquitectura, pero son igual de bloqueantes y no se han abordado todavía:

1. **Entidad legal en España**: no está confirmado que ya exista una empresa registrada que pueda ser la "client wallet" ante Rapyd Europa — sin esto no se puede ni empezar el KYB.
2. **Alineación con Andrés sobre el nuevo alcance**: todo este plan asume que Diving Planet es el "cliente piloto" de un producto que luego se vende a otros dive shops. Eso es un salto grande desde "un chatbot a medida" — no se ha confirmado que Andrés esté de acuerdo con ese cambio de rol (exclusividad, expectativas, qué gana él a cambio de ser el piloto).
3. **Propiedad intelectual del código**: si Diving Planet paga por "el chatbot" y dentro de ese proyecto se construye una plataforma completa de reservas+pagos, hay que separar por contrato el **core de la plataforma** (reutilizable, propiedad de quien la construye, licenciado a cada tenant) de la **configuración específica de Diving Planet** (`TenantConfig`, su branding, sus datos). Sin esa separación explícita por escrito, el modelo de negocio de "vender esto a otros" queda en el aire legal.
4. **Contrato actual con Diving Planet y Roverd**: no se ha preguntado si hay permanencia, aviso previo de cancelación o coste de salida con Roverd — podría condicionar los tiempos de la Fase 9 (migración/corte).
5. **Presupuesto y recursos**: no hay una estimación de cuánto tiempo/dinero cuesta llegar a la Fase 2 (MVP con pagos reales), ni quién del equipo se dedica a construirlo.

**Recomendación**: los puntos 2 y 3 son en realidad la misma conversación con Andrés — conviene resolverlos antes de seguir invirtiendo tiempo en cotizar proveedores de pago, porque si no se alinean bien desde el principio, el resto del plan puede quedar construido sobre una base que luego haya que renegociar.

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

### Cómo se cobra la comisión sin ser nosotros un banco: el mecanismo general (explicado con Stripe Connect, el ejemplo mejor documentado)

**Nota de estado**: esta sección explica el mecanismo general de "payment facilitator" usando Stripe Connect como ejemplo de libro de texto (es el más documentado del mercado). El proveedor real elegido para construir esto es **Rapyd/PayU** (§5), no Stripe — Stripe queda descartado como cuenta de plataforma porque Colombia no es país soportado (ver más abajo). Se mantiene esta explicación porque el concepto (cuenta del negocio + reparto automático de comisión) es idéntico en Rapyd, solo cambian los nombres técnicos (`wallets`+`split` en vez de `cuenta conectada`+`application_fee_amount`).

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

**Actualización — Opción C, la recomendada**: la investigación de proveedores (§5) encontró una tercera vía mejor que A y B: **Rapyd/PayU permite que tanto nosotros como Diving Planet operemos cada uno como empresa propia en su país** (España y Colombia respectivamente), sin entidad puente ni Merchant of Record improvisado — ver "Encaje geográfico confirmado" en §5. Esta es ahora la opción recomendada; A y B quedan como alternativas de respaldo si Rapyd/PayU no cierra en condiciones aceptables.

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
                 │+Capacity│ │ (Rapyd/PayU  │ │ (email/SMS)│
                 │ +Hold   │ │  u otro, §5) │ └───────────┘
                 └────────┘ └──────┬───────┘
                                   │ split / application_fee_amount
                                   ▼
                         ┌───────────────────┐
                         │ Nuestra client     │  ← ingreso real del negocio
                         │ wallet (plataforma)│
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

- `Tenant` (negocio: Diving Planet, y futuros forks) — incluye `payment_provider_account_id` (genérico: wallet de Rapyd/PayU u otra cuenta conectada según el proveedor elegido en §5) y `application_fee_percent`.
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

- **Estrategia principal actual (actualizado)**: Rapyd/PayU (§5, estudio en profundidad), porque resuelve tanto el tramo internacional como el colombiano bajo un solo proveedor, con Colombia y España soportados como países propios (sin entidad puente). Stripe Connect queda como fallback (Opción A) solo si Diving Planet o nosotros ya tuviéramos una entidad en país soportado por Stripe.
- **Internacional (USD, tarjeta) — mecánica de referencia con Stripe Connect**: cuentas conectadas tipo Standard, `destination charge` + `application_fee_amount`. Útil como comparación de costes (ver tablas más abajo), no es ya la vía principal a construir.
- **Colombiano (COP, Llave/Bancolombia/ACH, 50% del pago hoy)**: pendiente de investigar en Fase 0 de pagos si Wompi/ePayco/PayU soportan un modelo de marketplace equivalente. Si no, alternativas a evaluar: (a) arrancar monetizando solo el tramo USD y dejar el COP con el flujo actual (Roverd o manual) hasta resolver esto, o (b) un modelo de payout manual/programado con revisión legal previa (nos acerca más a ser money transmitter de facto — no decidir sin abogado local).
- **Bloqueo confirmado — Colombia no es país Stripe**: independientemente del tramo COP, ni siquiera el tramo USD puede montarse con Diving Planet como cuenta conectada propia, porque Stripe no admite empresas colombianas (ver detalle y opciones A/B en §1). Hay que decidir entre que Diving Planet monte una entidad en país soportado (Opción A) o que nosotros seamos el Merchant of Record (Opción B) antes de diseñar el `Payment` de la Fase 2.
- **DCC (conversión de moneda dinámica)**: se confirmó en el checkout real de Roverd que el propio gateway convierte a la divisa local del cliente con su propio tipo de cambio (ver `docs/questions_for_owner_business_kb.md` #43). Para nuestra plataforma, cobrar siempre en USD nativo (sin DCC) o ser transparentes sobre el tipo de cambio aplicado es una ventaja competitiva concreta y diferenciadora frente a Roverd, no solo paridad.
- **Reserva con hold temporal**: el checkout real de Roverd bloquea el cupo con cuenta regresiva mientras se completa el pago. Nuestro `Booking` necesita un estado `holding` con TTL (natural en Redis, ya usado en este repo vía `state_store.py`) antes de pasar a `confirmed` — sin esto, dos clientes pueden ver el mismo cupo libre a la vez y hay sobreventa real con dinero de por medio.
- **Cupones/promo codes**: el checkout real de Roverd los soporta; el modelo de `Payment` debe contemplarlo desde el diseño.
- **Fin de la conciliación manual**: hoy el owner transcribe a mano cada reserva al Excel `RESERVAS 2026` (columna "Pago": ROVERD/PADI/CXC). Con webhooks de Stripe actualizando `Payment` en tiempo real, el manifiesto diario (certificación, talla BCD, hotel, país, estado de pago) debería generarse solo desde `Booking`+`Customer`+`Payment` — cero transcripción manual es el criterio de éxito de la Fase 2.

### Cuánto se queda Stripe realmente (tablas de referencia/comparación — Stripe ya no es la vía principal, ver arriba)

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
- **La descripción del producto de marketplace dice explícitamente**: *"permite liquidar en tu moneda preferida, mientras los vendedores reciben sus fondos en la suya"* — sugiere que este producto (a diferencia del checkout estándar heredado de "PayU Colombia") sí tiene la flexibilidad de moneda que promociona Rapyd. No es una confirmación 100% oficial para nuestro caso, pero es una señal fuerte a favor.

**Hallazgo grande: Colombia SÍ es país soportado por Rapyd para abrir una cuenta de negocio propia — resuelve (a favor) el mayor riesgo pendiente**:
- Confirmado directamente: Colombia está en la lista de países donde Rapyd permite abrir una **Rapyd Business Account**, junto con Brasil, Chile, República Dominicana, El Salvador, México, Perú, entre otros en América. A diferencia de Stripe, **Rapyd sí permite que una empresa colombiana sea la propia cuenta de plataforma/partner** — no haría falta que nosotros (ni Diving Planet) montemos una entidad extranjera.
- **Tiempo de activación de la cuenta Rapyd** (proceso distinto y más largo que el de activar tarjetas internacionales sobre una cuenta PayU ya existente): puede tardar **hasta 30 días**, dependiendo del país y la documentación requerida (escritura de constitución, estructura organizativa, comprobante de domicilio).

**Pagos internacionales/extranjeros — confirmado que sí se pueden gestionar, con matices importantes**:

- **Activación**: se solicita por correo a `sac@payulatam.com` desde el email registrado en la cuenta, respondiendo un cuestionario (país de constitución legal, sector/actividad económica, esquema de negocio — qué se vende y cómo se entrega —, canales de venta, ticket promedio y máximo, canal de atención de reclamos, motivo de la solicitud). **Tiempo de aprobación: 2-5 días hábiles**, sujeto a la discreción de los socios bancarios de PayU (no automático ni garantizado).
- **Costo de activación**: la activación en sí **no tiene costo adicional** sobre la cuenta.
- **Tarifa por transacción internacional**: confirmado que las tarjetas internacionales usan **"una cuenta y tarifa separadas de las tarjetas locales"** — es decir, el 3.49%+800 COP es solo para tarjetas domésticas, y sí existe un recargo para tarjetas internacionales, pero **el % exacto no es público** — hay que preguntarlo directamente en la llamada.
- **Hallazgo importante que contradice la promesa general de Rapyd — liquidación forzada en COP**: la documentación de PayU Colombia dice explícitamente: *"Todos los pagos se retirarán en tu moneda local en una cuenta bancaria registrada en tu país."* Es decir, el producto **PayU Colombia liquida siempre en COP a una cuenta bancaria colombiana**, sin importar en qué moneda pagó el cliente extranjero — contradice la promesa de marketing más general de Rapyd de "liquida en la moneda que elijas" (esa flexibilidad puede existir solo en el producto de marketplace/plataforma de Rapyd, aún sin cotizar, no en la cuenta estándar de comercio heredada de PayU). **Esto hay que aclararlo explícitamente en la llamada** — cambia el diseño si Diving Planet nunca recibe USD limpios sino siempre COP ya convertidos.
- **Fee de conversión de moneda de Rapyd** (a nivel de marca general, no confirmado específico para Colombia): **1.00% por operación de FX**, aplicando el tipo de cambio diario propio de Rapyd (no el de la red de la tarjeta) — coherente con el 1-2% que ya vimos en Stripe, ningún proveedor da la conversión gratis.

**Encaje geográfico confirmado: plataforma en España + sub-merchant en Colombia + clientes de todo el mundo**

El equipo (nosotros, la plataforma) vive en España; Diving Planet está en Cartagena de Indias; los clientes finales son de todo el mundo. Este reparto **encaja de forma natural con el modelo de marketplace** — de hecho es el caso de uso central para el que Rapyd se posiciona, no una excepción a resolver:

- **España**: Rapyd opera en la UE/EEE a través de **Rapyd Europe hf.**, una entidad autorizada como Institución de Dinero Electrónico (EMI) por el Banco Central de Islandia, con pasaporte para operar en toda la UE/EEE — España incluida. Nuestra "client wallet" (la plataforma) encajaría aquí.
- **Colombia**: confirmado arriba, Diving Planet (sub-merchant) encaja en la cobertura LatAm de Rapyd (heredada de PayU GPO).
- **Clientes globales**: Rapyd es adquirente directo de Visa/Mastercard en múltiples regiones (UK, Europa, LatAm, Hong Kong, Israel, Singapur) — construido para procesar tarjetas de cualquier origen.
- El propio marketing de Rapyd describe literalmente este escenario como su propuesta de valor: ayudar a negocios a **"vender en LatAm sin necesidad de establecer entidades legales locales, abrir cuentas bancarias regionales, ni lidiar con leyes fiscales extranjeras complejas"** — es exactamente nuestra situación (equipo en España operando hacia Colombia).

**Matiz nuevo a confirmar en la llamada — entidades regulatorias regionales distintas**: Rapyd opera mediante entidades legales separadas por región — `Rapyd Europe hf.` para la UE/EEE, y una estructura de licencias distinta para LatAm (heredada de PayU). Esto significa que, técnicamente, nuestra cuenta de plataforma en España y la wallet de Diving Planet en Colombia podrían vivir bajo **dos entidades regulatorias distintas del mismo grupo Rapyd**. No hay señal de que esto sea un problema (es su propuesta de valor central), pero hay que confirmar explícitamente si un solo producto de marketplace puede enlazar una "client wallet" abierta bajo Rapyd Europa con "sub-merchant wallets" bajo Rapyd LatAm de forma nativa, o si requiere algún contrato/integración adicional entre ambas entidades del grupo.

**Sin confirmar todavía (no investigable por web, requiere hablar con ventas)**:
- **Si el enlace entre la "client wallet" bajo Rapyd Europa (España) y las "sub-merchant wallets" bajo Rapyd LatAm (Colombia) es nativo dentro de un solo producto de marketplace, o requiere una integración/contrato adicional entre ambas entidades regionales del grupo.**
- El % de fee específico del producto de marketplace/split (la tarifa de 3.49%+800 COP es solo la de aceptación estándar doméstica) y la estructura MDR + Interchange++ que usa Rapyd para tarjetas — el pricing del marketplace es negociado caso por caso (volumen, geografía, riesgo), no hay tabla pública.
- El % de recargo exacto para tarjetas internacionales (confirmado que existe una tarifa separada, no el número).
- **Si la liquidación puede ser en USD, o siempre es en COP a cuenta colombiana para nuestro caso concreto** — la pista del producto de marketplace (liquidar "en tu moneda preferida") es positiva pero no es confirmación oficial; sigue siendo la pregunta más importante para la llamada.
- Tiempos reales de liquidación/settlement al sub-merchant (frecuencia, no solo el tiempo de activación de la cuenta).

~~Si el "client wallet"/partner (nosotros, la plataforma) también necesita ser una entidad de un país concreto~~ — **resuelto**: Colombia está en la lista de países soportados por Rapyd para abrir cuenta de negocio propia, ver hallazgo arriba.

**Valoración**: con el hallazgo de que Colombia sí es país soportado por Rapyd para la cuenta de plataforma, esta pasa a ser claramente la mejor opción del mercado para nuestro caso — resuelve el riesgo más grande que teníamos (país del partner), tiene tarifa base pública y razonable, alta simple para empresa colombiana ya constituida, activación de pagos internacionales con proceso y plazo conocidos, y un producto de marketplace real con señales de flexibilidad de moneda. Las dudas que quedan (comisión exacta del marketplace, recargo internacional, y si la liquidación real permite USD) son de las que solo se resuelven hablando con ventas — siguiente paso concreto: contactar a Rapyd/PayU Colombia para cotizar el producto de marketplace y cerrar estas últimas incógnitas.

## 6. Fases

### Fase 0 — Discovery y validación del modelo de negocio (sin código)
- **Pagos — decisión bloqueante**: elegir Opción A (Diving Planet constituye entidad en país soportado por Stripe) vs. Opción B (nosotros como Merchant of Record) vs. **Opción C (proveedor LatAm nativo — PayU/Rapyd, dLocal o EBANX como marketplace, Diving Planet como sub-merchant real)** — ver §1 y §5. Confirmar con el owner cómo/con qué frecuencia le paga Roverd hoy (pregunta #44 de `docs/questions_for_owner_business_kb.md`) como referencia de mínimo aceptable.
- **Contactar a Rapyd/PayU Colombia** (candidato principal, ver estudio en §5): cotizar el producto de marketplace/split y confirmar la moneda de liquidación real (COP vs. USD) para nuestro caso — el requisito de país del partner ya se resolvió (Colombia sí es país soportado por Rapyd). En paralelo, pedir cotización equivalente a dLocal y EBANX como comparación.

  **Checklist para preparar el contacto (antes de escribirles)**:
  - [ ] Resumen de una página: qué es la plataforma (booking + pagos para dive shops/tour operators, modelo marketplace), quién es el primer cliente real (Diving Planet), y qué producto se necesita específicamente (marketplace/split payments, no aceptación estándar).
  - [ ] Volumen real estimado (reservas/mes y ticket medio de Diving Planet) — piden esto en el primer contacto, sin esto la conversación queda coja.
  - [ ] Decidir qué entidad legal será el "partner"/plataforma de cara al proveedor (¿existe ya y en qué país?) — es la pregunta que todos van a hacer primero.
  - [ ] Canal correcto por proveedor, no soporte genérico:
    - Rapyd: formulario de contacto comercial / sección "Marketplaces" en rapyd.net — mencionar explícitamente su producto de "Platforms" y Colombia.
    - dLocal: página "dLocal for Platforms" (formulario de demo/contacto) — mencionar "split payments" y Colombia.
    - EBANX: contacto comercial en business.ebanx.com — mencionar su modelo de Merchant of Record y split hacia vendors.
  - [ ] Guion de preguntas para la primera llamada:
    1. ~~¿El partner/plataforma puede ser una empresa colombiana?~~ — resuelto por investigación: sí, Colombia es país soportado por Rapyd para cuenta de negocio propia. Confirmar solo el detalle de documentación/plazo real de activación (hasta 30 días según lo encontrado).
    2. ¿Cuál es la tarifa específica del producto de marketplace/split (no la de aceptación estándar)?
    3. ¿Cómo es el proceso de KYC/onboarding de cada sub-merchant y cuánto tarda?
    4. ¿Con qué frecuencia se liquida al sub-merchant?
    5. ¿Hay volumen mínimo para acceder a este producto, o vale para un negocio del tamaño de Diving Planet?
    6. ¿Cuál es el recargo exacto para tarjetas internacionales (ya confirmado que existe una tarifa separada de la doméstica 3.49%+800COP, falta el %)?
    7. **La liquidación al sub-merchant, ¿puede ser en USD, o siempre es en COP a una cuenta bancaria colombiana?** (la documentación pública de PayU Colombia dice que siempre se liquida en moneda local — hay que confirmar si el producto de marketplace de Rapyd cambia esto).
    8. Si la liquidación es en COP, ¿qué tipo de cambio se aplica y hay un fee de conversión adicional (Rapyd anuncia 1% de FX a nivel general — confirmar si aplica igual aquí)?
    9. **Nuestro equipo/plataforma está en España y el sub-merchant (Diving Planet) en Colombia** — ¿el producto de marketplace enlaza de forma nativa una "client wallet" bajo Rapyd Europa con "sub-merchant wallets" bajo Rapyd LatAm, o requiere algún contrato/integración adicional entre esas dos entidades regionales del grupo?
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

### Fase 2 — Pagos con el proveedor elegido (Rapyd/PayU candidato principal, ver §5) y comisión de plataforma
- Onboarding de Diving Planet como sub-merchant/wallet del proveedor elegido (o cuenta conectada Stripe Standard si se recurre a la Opción A de respaldo).
- Split/`application_fee_amount` en cada `Payment` — este es el primer euro/dólar de ingreso real del proyecto.
- Webhooks del proveedor actualizando `Payment`/`Booking` sin intervención manual.
- Sustituye el `booking_url` de Roverd, idealmente para ambos tramos (internacional y colombiano) si Rapyd/PayU cierra en buenas condiciones.
- Si el proveedor elegido no cubre bien el tramo colombiano, puede quedar para una Fase 2b separada con otro proveedor complementario (Wompi/ePayco).
- Criterio de salida de fase: 0 reservas del tramo cubierto requieren transcripción manual al Excel.

### Fase 3 — Widget de checkout embebible
- Componente embebible (branding por tenant) equivalente al modal real de Roverd: Fecha → Información → Check-Out, con cuenta regresiva de hold y campo de cupón.
- Es lo que permite a un negocio vender sin depender de nuestro panel ni del bot.

### Fase 4 — Waivers digitales
- Punto de partida: el texto del waiver que Diving Planet ya usa hoy en Roverd (pedido a Andrés, ver mensaje en §0) — no se redacta desde cero, se adapta y se revisa con un abogado colombiano (ver §7, validez legal del waiver).
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
- **Regulatorio de pagos — mayormente resuelto**: Colombia no es país soportado por Stripe (confirmado, §1), pero **sí lo es por Rapyd** (§5) — Diving Planet puede ser sub-merchant/wallet con entidad propia colombiana, sin entidad puente ni nosotros como Merchant of Record improvisado. Queda pendiente confirmar solo el matiz de si el enlace entre la client wallet en España (Rapyd Europa) y el sub-merchant en Colombia (Rapyd LatAm) es nativo o requiere integración adicional (pregunta #9 del guion de la llamada, §6 Fase 0). Si Rapyd/PayU no cerrara en condiciones aceptables, se recurre a Opción A/B de Stripe (riesgo entonces sí aplica tal como se describía antes).
- **Riesgo de disputas/chargebacks**: con Rapyd/PayU como sub-merchant real, el riesgo queda en la cuenta de cada tenant (igual que la Opción A de Stripe), no en la nuestra — confirmar esto explícitamente en la llamada de ventas, no darlo por hecho solo por analogía con cómo funciona en general un marketplace.
- **Cumplimiento PCI**: no tocar datos de tarjeta directamente — usar Stripe Elements (hosted fields tokenizados), igual que ya hace Roverd hoy según la prueba en vivo del checkout.
- **Continuidad operativa durante la migración**: Diving Planet opera con buceadores reales todos los días; cualquier corte debe ser progresivo y reversible.
- **Alcance vs. marketing de Roverd**: no todo lo que roverd.com promete está en uso real por el cliente — verificar antes de invertir esfuerzo en Fase 8.
- **Relación con el chatbot actual**: `booking_agent.py` es hoy un stub — este proyecto lo reemplaza por una integración real contra la nueva API.

### Validez legal del waiver digital en Colombia (investigado)

- **La firma electrónica en sí es válida**: la Ley 527 de 1999 da a la firma electrónica la misma fuerza que la firma manuscrita, con presunción de que el firmante quiso autenticar el documento y quedar vinculado por su contenido. El mecanismo de firmar en pantalla no tiene problema legal.
- **Pero el contenido del waiver sí tiene un riesgo legal real**: el Estatuto del Consumidor (Ley 1480 de 2011) establece que las cláusulas que limitan la responsabilidad legal del proveedor son **"ineficaces de pleno derecho"** — nulas automáticamente. Un waiver que pretenda exonerar completamente a Diving Planet de cualquier responsabilidad (incluida negligencia) probablemente no tenga el efecto de blindaje total que parece tener en el papel — patrón común en muchas jurisdicciones (no se puede renunciar a reclamar por negligencia grave, aunque sí documentar que el cliente conocía y aceptó los riesgos inherentes de la actividad).
- **Conclusión práctica**: el waiver sigue siendo útil (documenta consentimiento informado, es evidencia en litigio, disuade reclamaciones frívolas), pero no debe venderse como blindaje legal total. Necesita redacción cuidadosa (reconocimiento de riesgo, no exoneración de negligencia) — **hace falta un abogado colombiano especializado en responsabilidad civil/consumo** para el texto final, no solo para el mecanismo de firma. Bloquea la Fase 4, no el modelo de ingreso.

### Protección de datos: RGPD + Ley 1581 de Colombia (investigado)

- **Lado colombiano**: Ley 1581 de 2012 + Decreto 1377 de 2013 (Habeas Data) exigen consentimiento, política de tratamiento, derechos de acceso/rectificación/supresión, y registro obligatorio en el **RNBD (Registro Nacional de Bases de Datos)** de la SIC — pero solo obligatorio si los activos totales de la empresa superan **100.000 UVT** (umbral alto, probablemente no aplica a Diving Planet directamente, pero sí podría aplicarnos a nosotros como plataforma si escalamos).
- **Lado europeo — hallazgo importante**: Colombia **no está en la lista de países con decisión de adecuación del RGPD** (esa lista incluye Argentina, Uruguay, Japón, Reino Unido... pero no Colombia). Cualquier transferencia de datos personales entre nuestra plataforma (España) y Colombia necesita salvaguardas adicionales — típicamente **cláusulas contractuales tipo (SCC, Decisión 2021/914)**, no basta un contrato normal.
- **Implicación de diseño**: el modelo `Customer` (certificación de buceo, pasaporte, etc.) maneja datos sensibles de por sí — hay que incorporar SCCs en el contrato con cada tenant y diseñar consentimiento/política de privacidad pensando en ambos marcos a la vez. Es tarea de abogado, pero ya se sabe exactamente qué mecanismo legal hace falta (SCC), no es una incógnita abierta.

### Aspectos fiscales de operar como intermediario España-Colombia (investigado)

- **Impuesto sobre la renta — buena noticia**: existe un Convenio de Doble Imposición España-Colombia (en vigor desde 2008, Ley 1082 de 2006). Confirmado: Colombia **no puede aplicar retención en la fuente** sobre las comisiones que recibe una empresa española, **siempre que esa empresa no opere a través de un establecimiento permanente en Colombia**. Además, la DIAN interpreta que si el servicio es una **aplicación totalmente automatizada** (no "servicio técnico"), no hay retención ni IVA colombiano sobre esa comisión — favorece el modelo de plataforma automatizada que estamos diseñando, mientras no montemos oficina/presencia fija en Colombia.
- **Punto de atención en España — el "caso Fénix"**: una plataforma de intermediación de pagos en España tributa IVA sobre el **importe íntegro cobrado al cliente, no solo sobre su comisión**, si se considera que actúa "en nombre propio" (asume responsabilidad ante el cliente, controla la comunicación, fija las condiciones). Si actúa como intermediario transparente (el cliente sabe que compra a Diving Planet, nosotros solo procesamos el pago), tributa solo sobre la comisión.
- **Implicación de diseño (refuerza una decisión ya tomada por otro motivo)**: el checkout y las comunicaciones deben dejar claro que el vendedor es Diving Planet, no nosotros — la misma decisión de diseño que ya recomendamos para evitar los problemas del modelo "Merchant of Record" puro (§1), ahora reforzada también por un motivo fiscal.

### Legal — pendientes adicionales sin abordar todavía

- **Contrato de servicio con Diving Planet (y cada tenant futuro)**: no solo el % de comisión — falta definir SLA, límites de responsabilidad (¿qué pasa si el sistema falla y se pierde/duplica una reserva con dinero de por medio?), indemnización, y ley aplicable/jurisdicción para disputas (¿España? ¿Colombia?).
- **Términos y condiciones + política de privacidad de cara al cliente final** (el buceador que reserva): necesarios para el checkout, y conectados directamente con el "caso Fénix" de arriba — debe quedar escrito y visible que el vendedor es Diving Planet, no nosotros.
- **Seguro de responsabilidad civil / errores y omisiones** para nosotros como plataforma que maneja dinero de terceros y datos sensibles (pasaportes, certificaciones).
- **Derecho de desistimiento de la UE (14 días)**: probablemente exento por tratarse de un servicio de ocio en fecha concreta (la Directiva 2011/83/UE excluye expresamente "servicios relacionados con actividades de ocio si el contrato prevé una fecha específica"), pero hay que **confirmarlo**, no darlo por hecho — afecta directamente a la política de reembolsos del checkout.
- **Registro Nacional de Turismo (RNT) en Colombia**: sin confirmar si una plataforma de reservas turísticas (no solo el operador) necesita registrarse ante las autoridades turísticas colombianas.
- **Obligaciones AML/KYC heredadas como partner de Rapyd**: al ser nosotros el "client wallet" con varios sub-merchants, es posible que heredemos alguna obligación propia de monitorización/reporte de actividad sospechosa sobre nuestros tenants (no solo Rapyd vigilando, nosotros como plataforma también) — confirmar en la llamada de ventas qué responsabilidad de compliance recae sobre el partner.
- **Riesgo de marca/nombre**: evitar que el nombre comercial del producto se parezca demasiado a "Roverd" u otras marcas del sector — revisión básica de marca antes de lanzar comercialmente.
- **¿Necesitamos licencia/registro propio en España para operar como partner de Rapyd?**: la misma pregunta que ya nos hicimos con Stripe (¿podemos actuar como agregador sin autorización propia?) nunca se hizo específicamente para Rapyd. Operar bajo el paraguas de `Rapyd Europe hf.` (su licencia EMI) puede eximirnos de necesitar registro propio como agente de servicios de pago bajo PSD2 en España, o puede requerir un alta como "agente vinculado" — no confirmado, y es el mismo tipo de riesgo regulatorio que ya nos hizo descartar un MoR "a pelo" sobre Stripe. Pregunta obligatoria para la llamada de ventas con Rapyd.

### Financiero — pendiente adicional sin abordar todavía

- **Riesgo de tesorería / exposición a tipo de cambio propia**: si retenemos fondos en escrow en varias monedas (COP, USD, posiblemente EUR) antes de liquidar a cada tenant, quedamos expuestos a la fluctuación del tipo de cambio mientras el dinero está "de paso" por nuestra wallet — no es solo el 1% de fee de conversión que cobra Rapyd, es un riesgo financiero real si el peso colombiano se mueve fuerte entre el cobro y la liquidación. No se ha modelado ni decidido si conviene liquidar lo antes posible para minimizar esta exposición.

### Código/Arquitectura — pendientes adicionales sin abordar todavía

- **Fiabilidad de webhooks**: idempotencia, verificación de firma, reintentos — diseñar qué pasa si el webhook del proveedor de pago llega duplicado o si nuestro servidor está caído cuando llega (mismo patrón que el poller de Chatwoot ya usado en el bot para mensajes perdidos, aplicado ahora a pagos).
- **Idempotencia en las peticiones del cliente**: un reintento de red al crear un hold o confirmar un pago no debe generar dos reservas o dos cobros — requiere idempotency keys en la API, no solo en los webhooks entrantes.
- **Abuso del sistema de hold**: alguien podría bloquear cupo repetidamente sin pagar nunca (una especie de "hold DoS") — el mecanismo diseñado para evitar sobreventa abre esta puerta si no se limita (rate limiting, límite de holds simultáneos por IP/sesión).
- **Modelo de dinero**: enteros/centavos en vez de decimales flotantes, y ojo con COP que tiene **0 decimales** (visto en la documentación de dLocal) — un bug de redondeo aquí es dinero real perdido.
- **Auditoría inmutable de transacciones**: un log de solo-escritura separado de `Payment`/`Booking` (que sí se pueden actualizar) para reconstruir qué pasó exactamente ante una disputa o auditoría.
- **Entornos de prueba (sandbox) separados de producción**: probar contra el modo sandbox de Rapyd/Stripe antes de mover dinero real — no se ha definido la estrategia de entornos (dev/staging/prod) para el nuevo servicio.
- **Contrato de integración entre el bot actual y el nuevo servicio**: seguimos sin definir cómo exactamente `booking_agent.py` (hoy un stub) llamaría a la nueva API — endpoints, autenticación, versión.

### Infraestructura — pendientes adicionales sin abordar todavía

- **Punto único de fallo**: el bot corre hoy en un solo VPS Hetzner (CX23) con Docker Compose — aceptable para un chatbot, pero un sistema que mueve dinero real probablemente necesite mejor tolerancia a fallos.
- **Monitorización y alertas**: no hay definido un sistema de alertas (ej. Sentry, health checks) que avise si fallan pagos, webhooks, o la reconciliación — crítico para detectar problemas antes de que los detecte el cliente.
- **Gestión de secretos**: hoy se usan archivos `.env` (visto en `session-handoff.md`) — con múltiples tenants y sus propias API keys del proveedor de pago, esto probablemente necesite algo más serio que un `.env` compartido.
- **Backups/disaster recovery de la base de datos de pagos**: mucho más crítico que el de la KB del bot — no se ha definido política de backup ni de retención.

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
