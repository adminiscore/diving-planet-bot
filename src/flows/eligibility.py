"""Age & certification eligibility — single source of truth.

Centralizes "what can each person do" so the bot can offer services adapted to
each member of a group and clearly inform what is and isn't possible given age
and certification limitations.

Rules (from data/knowledge_base: faqs `age_minimum`, `Bubble Makers`, policies,
and services.json `min_age`):
- Snorkel: from 6 years old.
- Bubble Makers (intro dive for kids — pool / very shallow water, max 2 m): 8-10.
- Dive mini-course (bautismo / discover scuba): from 10.
- PADI Open Water: from 10 (owner 2026-09-14); Advanced and Rescue: from 12 (Gadea 2026-10-26). Divemaster 18.
- Certified fun dives: require an Open Water certification (and age >= 10).
- Under 6: no in-water activity yet — can come along as a companion.
- Minors must be accompanied by a responsible adult.
"""

from __future__ import annotations

from src.domain import activities as dom

# --- Age thresholds ---------------------------------------------------------
# Salen del registro de actividades (`min_age`/`max_age` de activities.json), la
# fuente unica: antes estaban escritas aqui y en el registro, y el cambio de
# Advanced/Rescue a 10 (owner 2026-09-14) hubo que hacerlo en los dos sitios.
MIN_SNORKEL = dom.by_id("snorkel").min_age
BUBBLE_MAKERS_MIN = dom.by_id("bubble_makers").min_age
BUBBLE_MAKERS_MAX = dom.by_id("bubble_makers").max_age
MIN_DIVE = dom.by_id("minicourse").min_age          # mini-course + Open Water
MIN_ADVANCED = dom.by_id("padi_advanced").min_age    # Advanced / Rescue
MIN_DIVEMASTER = dom.by_id("padi_divemaster").min_age

# Canonical activity keys used across the flow.
SNORKEL = "snorkel"
BUBBLE_MAKERS = "bubble_makers"
MINICOURSE = "minicourse"
OPEN_WATER = "open_water"
CERTIFIED_DIVING = "certified_diving"
COMPANION = "companion"


def is_minor(age: int) -> bool:
    return age < 18


def beginner_options_for_age(age: int | None) -> list[str]:
    """Offer options (ordered) for a NON-certified person of this age.

    `age is None` -> unknown age, assume an adult beginner (all beginner options).
    Companion ("just come along") is always the last fallback. Bubble Makers is
    only for 8-10; the adult mini-course only from 10.
    """
    if age is None:
        return [MINICOURSE, SNORKEL, COMPANION]
    if age < MIN_SNORKEL:                 # <6: nothing in water
        return [COMPANION]
    if age < BUBBLE_MAKERS_MIN:           # 6-7: snorkel only
        return [SNORKEL, COMPANION]
    if age < MIN_DIVE:                    # 8-9: Bubble Makers or snorkel
        return [BUBBLE_MAKERS, SNORKEL, COMPANION]
    return [MINICOURSE, SNORKEL, COMPANION]   # 10+


# Clave de opcion de este modulo -> id del registro de actividades (F3b).
_OPTION_TO_ACTIVITY = {
    CERTIFIED_DIVING: "certified_diving",
    MINICOURSE: "minicourse",
    BUBBLE_MAKERS: "bubble_makers",
    SNORKEL: "snorkel",
    OPEN_WATER: "padi_open_water",
}


def option_activity_id(option: str) -> str:
    """Id del registro de actividades para una opcion de este modulo."""
    return _OPTION_TO_ACTIVITY.get(option, option)


def age_eligibility_note(age: int, lang: str = "es") -> str:
    """A short, positive, clear sentence about what a person of this age can do.

    Always frames it constructively (never "can't do anything"); when an
    activity isn't available yet, it points to what IS available.
    """
    if lang == "es":
        if age < MIN_SNORKEL:
            return (
                f"Con {age} años todavía no puede entrar al agua en nuestras actividades "
                f"(el snorkel es desde los {MIN_SNORKEL} años), ¡pero puede acompañar al grupo "
                "y disfrutar del paseo en lancha y las islas! 🐠"
            )
        if age < BUBBLE_MAKERS_MIN:        # 6-7
            return (
                f"¡Con {age} años puede hacer *snorkel* y disfrutar del arrecife desde la superficie! 🌊 "
                f"El buceo (Bubble Makers) es a partir de los {BUBBLE_MAKERS_MIN} años y el minicurso desde los {MIN_DIVE}."
            )
        if age < MIN_DIVE:                  # 8-9
            return (
                f"¡Con {age} años tiene dos planazos! 🤿 Puede hacer *snorkel* (desde los {MIN_SNORKEL}) "
                f"o el programa *Bubble Makers* (buceo introductorio para niños de {BUBBLE_MAKERS_MIN} a {BUBBLE_MAKERS_MAX} años, "
                "en piscina o aguas muy poco profundas, máx. 2 m, con instructor dedicado). "
                f"El minicurso de buceo y los cursos ya son desde los {MIN_DIVE} años."
            )
        # 10+
        base = (
            f"¡Con {age} años puede hacer *snorkel*, el *minicurso de buceo* y el curso *Open Water*! 🎉 "
        )
        if age < MIN_DIVEMASTER:          # 10-17
            base += (
                f"¡Y a esa edad ya puede hacer también los cursos *Advanced* y *Rescue* "
                f"(desde los {MIN_ADVANCED} años)! El *Divemaster* es a partir de los {MIN_DIVEMASTER}. "
            )
        else:                             # 18+
            base += "Y también todos los cursos PADI, incluido el *Divemaster*. "
        base += "Para las salidas como *buzo certificado* solo necesita tener la certificación Open Water."
        if is_minor(age):
            base += " (Los menores deben ir acompañados de un adulto responsable.)"
        return base

    # English
    if age < MIN_SNORKEL:
        return (
            f"At {age} years old they can't join the in-water activities yet "
            f"(snorkeling starts at {MIN_SNORKEL}), but they can come along with the group "
            "and enjoy the boat ride and the islands! 🐠"
        )
    if age < BUBBLE_MAKERS_MIN:
        return (
            f"At {age} they can do *snorkeling* and enjoy the reef from the surface! 🌊 "
            f"Diving (Bubble Makers) starts at {BUBBLE_MAKERS_MIN} and the mini-course at {MIN_DIVE}."
        )
    if age < MIN_DIVE:
        return (
            f"At {age} they have two great options! 🤿 *Snorkeling* (from {MIN_SNORKEL}) "
            f"or the *Bubble Makers* program (intro diving for kids {BUBBLE_MAKERS_MIN}-{BUBBLE_MAKERS_MAX}, "
            "in a pool or very shallow water, max 2 m, with a dedicated instructor). "
            f"The dive mini-course and courses start at {MIN_DIVE}."
        )
    base = (
        f"At {age} they can do *snorkeling*, the *dive mini-course* and the *Open Water* course! 🎉 "
    )
    if age < MIN_DIVEMASTER:            # 10-17
        base += (
            f"And at that age they can also take the *Advanced* and *Rescue* courses "
            f"(from {MIN_ADVANCED})! *Divemaster* starts at {MIN_DIVEMASTER}. "
        )
    else:                              # 18+
        base += "And all PADI courses too, including *Divemaster*. "
    base += "For *certified* fun dives they just need to hold an Open Water certification."
    if is_minor(age):
        base += " (Minors must be accompanied by a responsible adult.)"
    return base
