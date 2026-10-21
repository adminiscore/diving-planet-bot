# gen-6 · Origen (21-oct, Gonzalo con Claude)

**Causa 3 de G9** (del análisis por causas, sin abrir el examen), unos 8 fallos: "enlace o precio sin preguntar desde
dónde sale (o asumiendo Cartagena); repregunta el origen cuando ya lo dijo (un hotel de las islas, Barú)".

**Política** (`policies.json`, transporte): la recogida es solo en las Islas del Rosario. Barú no es parte de las islas:
allí no operamos ni recogemos, y quien se aloja en Barú sale desde Cartagena (Muelle de la Bodeguita).

## Diagnóstico (banco propio, base)

Banco `docs/robustness/gen/dialogos-gen6.json`, 10 diálogos, 2 repeticiones, con `--codigo-local` en PRE y código de
`pre_gadea` 51cc064:

- **Bien:** el precio sin origen (pregunta el origen antes de cotizar), el hotel de la base en las islas, Isla Grande
  en dos turnos y Cartagena contestado en dos turnos (sin repreguntar).
- **Mal, Barú:** a «Estamos hospedados en Barú» el bot vuelve a preguntar «¿Desde dónde saldrías?» (2/2). En Barú,
  Playa Blanca y el caso en inglés, el RAG dice bien «desde Barú se sale desde Cartagena», pero **el origen no se
  guarda** (0/8 turnos con origen). La reserva lo tiene pendiente y lo repregunta en el turno siguiente.

**Causa:** desde G3-06 (`baru_no_es_rosario`), Barú dejó de ser «las islas», pero tampoco pasó a ser nada. Jev
(`customer_place`) lo deja en «none» y el extractor descarta la cita. Con `lugar_con_dos_lectores`, un «none» de Jev
tumba además lo que lea el extractor. Y «Barú» ni siquiera contaba como lugar en la cita (`_lugares`).

Aparte, un defecto de la puerta del origen (`_sin_importes`): si el RAG escribe «…cuesta:», una línea en blanco y la
lista de precios, al quitar los importes se quedaba el título colgado («La salida de 2 inmersiones cuesta:» y luego la
pregunta del origen).

## Cambio (dos flags, APAGADOS)

- `BARU_SALE_DE_CARTAGENA`: quien se aloja en Barú o Playa Blanca es 'cartagena' para los tres lectores del lugar:
  - Jev `customer_place` (`_CUSTOMER_PLACE_Q_BARU_CARTAGENA`);
  - el extractor (`_BARU_SALE_DE_CARTAGENA` en la regla del origen, «Barú» y «blanca» como lugar y la cita de Barú → cartagena);
  - el resolutor de la pregunta del origen y el extractor de respaldo (`lugar_sin_baru(…, sale_de_cartagena)`).

  El RAG sigue avisando de que en Barú no se recoge.
- `ORIGEN_SIN_TITULO_SUELTO`: `_sin_importes` busca el título de la lista saltando las líneas en blanco.

## Medida

| Variante | Barú con origen Cartagena | Repregunta tras decir Barú | Lo demás del banco |
|---|---|---|---|
| Base | 0/8 | 2 | bien |
| `--flag baru_sale_de_cartagena` | **8/8** | **0** | igual |

Ficheros: `2026-10-21-gen6-base.jsonl` y `2026-10-21-gen6-con.jsonl`. La ronda core A/B sin desplegar (`gen6-A`,
`gen6-B`) va en el commit siguiente, con su juicio.
