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

from dataclasses import dataclass, field

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


@dataclass
class PersonPlan:
    """What one person (or homogeneous subgroup) can do."""
    who: str                      # short label, e.g. "buzo certificado", "9 años"
    qty: int = 1
    options: list = field(default_factory=list)   # ordered activity keys
    age: int | None = None

    @property
    def auto(self) -> str | None:
        """The single forced activity when there is only one option, else None."""
        return self.options[0] if len(self.options) == 1 else None


def plan_group(certified: int = 0, noncert_ages: list[int] | None = None,
               noncert_unknown: int = 0) -> list[PersonPlan]:
    """Build a per-subgroup plan from a known composition.

    - `certified`: how many hold an Open Water certification (fun dives).
    - `noncert_ages`: ages of non-certified people whose age is known.
    - `noncert_unknown`: non-certified people whose age is unknown (assume adults).

    Certified people share one line; non-certified people are grouped by the
    set of options their age allows (so two 9-year-olds share one entry).
    """
    noncert_ages = list(noncert_ages or [])
    plans: list[PersonPlan] = []
    if certified > 0:
        plans.append(PersonPlan(who="buzo certificado", qty=certified,
                                options=[CERTIFIED_DIVING]))

    # Non-certified people with a KNOWN age: one line per distinct age (so two
    # 9-year-olds merge into "9 años ×2", but a 12-year-old stays separate and
    # is never confused with an unknown-age adult).
    age_counts: dict[int, int] = {}
    for age in noncert_ages:
        age_counts[age] = age_counts.get(age, 0) + 1
    for age in sorted(age_counts):
        plans.append(PersonPlan(
            who=f"{age} años", qty=age_counts[age],
            options=beginner_options_for_age(age), age=age,
        ))

    # Non-certified people with UNKNOWN age (assume adults) get their own line.
    if noncert_unknown > 0:
        plans.append(PersonPlan(
            who="sin certificar", qty=noncert_unknown,
            options=beginner_options_for_age(None), age=None,
        ))
    return plans


_ACTIVITY_LABELS = {
    "es": {
        CERTIFIED_DIVING: "buceo certificado (salida de buceo)",
        MINICOURSE: "minicurso de buceo",
        BUBBLE_MAKERS: "Bubble Makers (buceo para niños 8-10)",
        SNORKEL: "snorkel",
        OPEN_WATER: "curso Open Water",
        COMPANION: "acompañante (sin actividad en el agua)",
    },
    "en": {
        CERTIFIED_DIVING: "certified fun dive",
        MINICOURSE: "dive mini-course",
        BUBBLE_MAKERS: "Bubble Makers (kids diving 8-10)",
        SNORKEL: "snorkeling",
        OPEN_WATER: "Open Water course",
        COMPANION: "companion (no in-water activity)",
    },
}


def format_group_plan(plans: list[PersonPlan], lang: str = "es") -> str:
    """A clear, positive per-person breakdown of what each can do."""
    labels = _ACTIVITY_LABELS[lang if lang in _ACTIVITY_LABELS else "es"]
    lines: list[str] = []
    for p in plans:
        opts = " / ".join(labels[o] for o in p.options)
        qty_prefix = f"{p.qty}× " if p.qty > 1 else ""
        if lang == "es":
            verb = "→ " if p.auto else "→ puede elegir: "
            lines.append(f"• {qty_prefix}*{p.who}* {verb}{opts}")
        else:
            verb = "→ " if p.auto else "→ can choose: "
            lines.append(f"• {qty_prefix}*{p.who}* {verb}{opts}")
    return "\n".join(lines)


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
        elif age < MIN_DIVEMASTER:
            base += f"El Divemaster es a partir de los {MIN_DIVEMASTER} años."
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
    elif age < MIN_DIVEMASTER:
        base += f"Divemaster starts at {MIN_DIVEMASTER}. "
    base += "For *certified* fun dives they just need to hold an Open Water certification."
    if is_minor(age):
        base += " (Minors must be accompanied by a responsible adult.)"
    return base
