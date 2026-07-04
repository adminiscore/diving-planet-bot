"""Age & certification eligibility — single source of truth.

Centralizes "what can each person do" so the bot can offer services adapted to
each member of a group and clearly inform what is and isn't possible given age
and certification limitations.

Rules (from data/knowledge_base: faqs `age_minimum`, `Bubble Makers`, policies,
and services.json `min_age`):
- Snorkel: from 6 years old.
- Bubble Makers (intro dive for kids — pool / very shallow water, max 2 m): 8-10.
- Dive mini-course (bautismo / discover scuba): from 10.
- PADI Open Water and courses: from 10 (Advanced/Rescue from 12, Divemaster 18).
- Certified fun dives: require an Open Water certification (and age >= 10).
- Under 6: no in-water activity yet — can come along as a companion.
- Minors must be accompanied by a responsible adult.
"""

from __future__ import annotations

# --- Age thresholds ---------------------------------------------------------
MIN_SNORKEL = 6
BUBBLE_MAKERS_MIN = 8
BUBBLE_MAKERS_MAX = 10
MIN_DIVE = 10          # mini-course + Open Water
MIN_ADVANCED = 12      # Advanced / Rescue
MIN_DIVEMASTER = 18

# Canonical activity keys used across the flow.
SNORKEL = "snorkel"
BUBBLE_MAKERS = "bubble_makers"
MINICOURSE = "minicourse"
OPEN_WATER = "open_water"
CERTIFIED_DIVING = "certified_diving"
COMPANION = "companion"


def activities_for_age(age: int) -> list[str]:
    """Ordered list of activity keys a person of the given age may do.

    Does not consider certification (see `can_fun_dive`). An empty list means
    no in-water activity — the person can still come as a companion.
    """
    if age < MIN_SNORKEL:
        return []
    if age < BUBBLE_MAKERS_MIN:            # 6-7
        return [SNORKEL]
    if age < MIN_DIVE:                      # 8-9
        return [SNORKEL, BUBBLE_MAKERS]
    # 10+  -> snorkel, mini-course, Open Water (fun dives need a certification too)
    return [SNORKEL, MINICOURSE, OPEN_WATER]


def can_snorkel(age: int) -> bool:
    return age >= MIN_SNORKEL


def can_bubble_makers(age: int) -> bool:
    return BUBBLE_MAKERS_MIN <= age <= BUBBLE_MAKERS_MAX


def can_minicourse(age: int) -> bool:
    return age >= MIN_DIVE


def can_take_courses(age: int) -> bool:
    return age >= MIN_DIVE


def can_fun_dive(age: int, is_certified: bool | None) -> bool:
    """Certified fun dives require an Open Water certification and age >= 10."""
    return age >= MIN_DIVE and bool(is_certified)


def is_minor(age: int) -> bool:
    return age < 18


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
            f"¡Con {age} años puede hacer *snorkel*, el *minicurso de buceo* y hasta el curso *Open Water*! 🎉 "
        )
        if age < MIN_ADVANCED:
            base += f"Los cursos Advanced/Rescue son desde los {MIN_ADVANCED} años."
        base += " Para las salidas como *buzo certificado* solo necesita tener la certificación Open Water."
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
        f"At {age} they can do *snorkeling*, the *dive mini-course* and even the *Open Water* course! 🎉 "
    )
    if age < MIN_ADVANCED:
        base += f"Advanced/Rescue courses start at {MIN_ADVANCED}. "
    base += "For *certified* fun dives they just need to hold an Open Water certification."
    if is_minor(age):
        base += " (Minors must be accompanied by a responsible adult.)"
    return base
