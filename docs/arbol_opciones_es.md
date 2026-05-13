# Árbol de opciones (ES) — actualizado desde `services.json`

Este documento refleja el árbol de decisión actual y los servicios disponibles en `data/knowledge_base/services.json`.

## Catálogo incorporado al árbol

- **Tours desde Cartagena**
  - **Salidas de Buceo - 2 inmersiones** (`2_dives_1_day`)
  - **Minicurso de Buceo** (`minicourse`)
  - **Tour de Snorkeling** (`snorkeling`)
  - **Servicio Privado** (`private`)
- **Tours / paquetes para clientes ya en las islas**
  - **Salidas de Buceo - 2 inmersiones (ya en las islas)** (`2_dives_1_day_already_on_island`)
  - **Paquete de 3 buceos (2 diurnos + 1 nocturno) - ya en las islas** (`3_dives_1_day_already_on_island`)
  - **Paquete de 5 buceos (2 dias) - ya en las islas** (`5_dives_2_days_already_on_island`)
  - **Paquete de 7 buceos (3 dias) - ya en las islas** (`7_dives_3_days_already_on_island`)
  - **Minicurso de Buceo (ya en las islas)** (`minicourse_already_on_island`)
  - **Tour de Snorkeling (ya en las islas)** (`snorkeling_already_on_island`)
- **Paquetes certificados desde Cartagena**
  - **5 Buceos - 2 dias** (`5_dives_2_days`)
  - **7 Buceos - 3 dias** (`7_dives_3_days`)
  - **9 Buceos - 4 dias** (`9_dives_4_days`)
- **Cursos PADI**
  - **Curso Basico PADI (Open Water)** (`open_water`)
  - **Curso Basico PADI (Open Water) - ya en las islas** (`open_water_already_on_island`)
  - **Curso Avanzado PADI** (`advanced`)
  - **Curso Avanzado PADI - ya en las islas** (`advanced_already_on_island`)
  - **Curso de Rescate + EFR** (`rescue`)
  - **Curso Referido (Open Water)** (`referral`)
  - **Curso Dive Master PADI** (`divemaster`)
- **Especialidades PADI**
  - **Especialidad Mindful Diving** (`mindful_diving`)
  - **Especialidad PADI: Naturalista** (`naturalist_specialty`)
  - **Especialidad PADI: Identificacion de Peces** (`fish_identification_specialty`)
  - **Especialidad PADI: Flotabilidad** (`buoyancy_specialty`)
  - **Especialidad PADI: Nitrox** (`nitrox_specialty`)
  - **Especialidad PADI: Identificacion de Peces - ya en las islas** (`fish_identification_specialty_already_on_island`)
  - **Especialidad PADI: Nitrox - ya en las islas** (`nitrox_specialty_already_on_island`)
  - **Especialidad PADI: Naturalista - ya en las islas** (`naturalist_specialty_already_on_island`)
  - **Especialidad PADI: Flotabilidad - ya en las islas** (`buoyancy_specialty_already_on_island`)

## Árbol visual

- **Idioma**
  - **Español**
    - **Menú principal**
      - **1. 🤿 Tours de buceo y snorkel (desde Cartagena)**
        - Fija `location = cartagena`.
        - **Tipo de grupo**
          - **1. Solo buzos certificados**
            - **Tours certificados desde Cartagena**
              - **1. Salidas de Buceo - 2 inmersiones**
                - Pregunta inactividad: **¿más de 2 años desde la última inmersión?**
                  - **Sí** → pregunta experiencia **500+ inmersiones / Dive Master**
                    - **Sí** → **Transferir con asesor/jefe**
                    - **No** → recomienda refresher → pregunta si quiere incluirlo
                      - **Sí** → cambia a `minicourse` como alternativa/refuerzo → pregunta colombiano/residente → resumen
                      - **No** → pregunta colombiano/residente → resumen
                  - **No** → muestra detalle del servicio → pregunta colombiano/residente → resumen
              - **2. 5 Buceos - 2 dias**
                - Muestra detalle desde `services.json`.
                - Flujo de inactividad/refresher igual que arriba.
                - Si acepta refresher, mantiene el paquete multi-día y deja anotación para asesor.
              - **3. 7 Buceos - 3 dias**
                - Muestra detalle desde `services.json`.
                - Flujo de inactividad/refresher igual.
              - **4. 9 Buceos - 4 dias**
                - Muestra detalle desde `services.json`.
                - Flujo de inactividad/refresher igual.
              - **5. Servicio Privado**
                - Explica que requiere revisar fecha, número de personas, experiencia, acompañantes/snorkelers y horarios.
                - **Transferir con asesor/jefe**
          - **2. Solo principiantes**
            - **Tours principiantes desde Cartagena**
              - **1. Minicurso de Buceo** → detalle desde `services.json` → pregunta ubicación si falta → pregunta colombiano/residente → resumen
              - **2. Tour de Snorkeling** → detalle desde `services.json` → pregunta ubicación si falta → pregunta colombiano/residente → resumen
              - **3. Servicio Privado** → explicación + transferencia
          - **3. Grupo mixto (buceo + snorkel)**
            - Explica que se puede combinar grupo con buzos, principiantes y snorkelers, pero puede requerir coordinación por seguridad.
            - **Transferir con asesor/jefe**
          - **4. Solo snorkel / acompañantes**
            - Selecciona `snorkeling` → detalle → pregunta colombiano/residente → resumen

      - **2. 🏝️ Ya estoy en las islas**
        - Fija `location = island`.
        - **Tipo de grupo**
          - **1. Solo buzos certificados**
            - **Tours certificados ya en islas**
              - **1. Salidas de Buceo - 2 inmersiones (ya en las islas)**
              - **2. Paquete de 3 buceos (2 diurnos + 1 nocturno) - ya en las islas**
              - **3. Paquete de 5 buceos (2 dias) - ya en las islas**
              - **4. Paquete de 7 buceos (3 dias) - ya en las islas**
              - **5. Servicio Privado**
            - Los servicios usan las variantes `*_already_on_island` cuando existen.
            - Flujo de inactividad/refresher igual; si el refresher aplica a un plan de 1 día, usa `minicourse_already_on_island`.
          - **2. Solo principiantes**
            - **1. Minicurso de Buceo (ya en las islas)**
            - **2. Tour de Snorkeling (ya en las islas)**
            - **3. Servicio Privado**
          - **3. Grupo mixto** → explicación + transferencia
          - **4. Solo snorkel / acompañantes** → `snorkeling_already_on_island`

      - **3. 📘 Cursos PADI y certificaciones**
        - **Menú cursos**
          - **1. Quiero certificarme (Open Water)**
            - Pregunta origen de práctica:
              - **Salgo desde Cartagena** → `open_water`
              - **Ya estoy en las islas** → `open_water_already_on_island`
            - Pregunta si tiene al menos 2 días completos.
            - Muestra detalle → pregunta colombiano/residente → resumen.
          - **2. Otro curso PADI avanzado/profesional**
            - Abre menú avanzado/especialidades:
              - **1. Curso Avanzado PADI** (`advanced` / `advanced_already_on_island` si location island)
              - **2. Curso de Rescate + EFR** (`rescue`)
              - **3. Curso Dive Master PADI** (`divemaster`)
              - **4. Especialidad Mindful Diving** (`mindful_diving`)
              - **5. Identificacion de Peces** (`fish_identification_specialty` / versión islas)
              - **6. Naturalista** (`naturalist_specialty` / versión islas)
              - **7. Flotabilidad** (`buoyancy_specialty` / versión islas)
              - **8. Nitrox** (`nitrox_specialty` / versión islas)
          - **3. Especialidades PADI**
            - Abre el mismo menú avanzado/especialidades para elegir especialidad.
          - **4. Ya empecé un curso en otro centro (referral / reactivate)**
            - Explica que debe revisarse eLearning, formularios PADI e inmersiones pendientes.
            - **Transferir con asesor/jefe**

      - **4. 💰 Precios y descuentos**
        - **1. Precios saliendo desde Cartagena**
          - Muestra referencias de `2_dives_1_day`, `minicourse`, `snorkeling`.
        - **2. Precios si ya estoy en las islas**
          - Muestra referencias de `2_dives_1_day_already_on_island`, `3_dives_1_day_already_on_island`, `minicourse_already_on_island`, `snorkeling_already_on_island`.
        - **3. Paquetes multi-día**
          - Muestra `5_dives_2_days`, `7_dives_3_days`, `9_dives_4_days`.
          - También muestra versiones islas `5_dives_2_days_already_on_island` y `7_dives_3_days_already_on_island`.
        - **4. Descuentos para colombianos/residentes**
          - Explica descuentos locales/COP y condiciones a confirmar por WhatsApp.

      - **5. 💳 Reserva y pagos**
        - **1. Pagar todo online**
        - **2. Pagar 50% ahora y 50% después**
        - **3. Formas de pago (tarjeta / transferencia)**
        - **4. Reservas de grupo o agencia**
        - Después vuelve al menú principal.

      - **6. ℹ️ Logística y otras preguntas**
        - **1. Punto de encuentro y horarios**
          - Cartagena: Muelle de la Bodeguita 8:00 a.m.; regreso aprox. 4:00-4:30 p.m.
          - Islas/multi-día: horarios coordinados según alojamiento y plan.
        - **2. Alojamiento en islas y recogida en hotel**
          - Va a selector de isla y luego hotel.
        - **3. Qué incluye / qué no incluye el plan**
          - Usa regla general y diferencia Cartagena vs. ya en islas.
        - **4. Qué llevar y recomendaciones**
          - Toalla, bloqueador, ropa cómoda, gorra/sombrero, medicación para mareo si aplica, clima y cancelaciones.

      - **7. 🧑‍💬 Hablar con un asesor**
        - **Transferir con asesor/jefe**

## Notas de implementación

- `src/flows/decision_tree.py` carga `SERVICES` desde `services.json`, por lo que nombres, precios, inclusiones, requisitos, itinerarios y booking links salen del catálogo actualizado.
- `ISLAND_SERVICE_MAP` convierte servicios base a sus variantes `*_already_on_island` cuando el usuario indica que ya está en las islas.
- Los servicios complejos, privados, grupos mixtos, referral/reactivate y excepciones se escalan a asesor porque el MVP no confirma disponibilidad, pagos finales ni reservas cerradas automáticamente.
