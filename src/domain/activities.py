"""Registro de actividades: la fuente UNICA de que vende el bot y para quien.

Carga `data/knowledge_base/activities.json` (editable por negocio) y expone lo que
hoy esta copiado en ~30 tablas repartidas por el codigo: ids canonicos, servicios
del catalogo por ubicacion, tipo de item del carrito, etiquetas y el contexto de
negocio (`for_whom`) que deben ver los prompts. Ver
docs/robustness/activity-domain-plan.md.

Modulo hoja a proposito: solo stdlib, sin importar nada de `src`, para que
cualquier capa (regex, prompts, nucleo, carrito, RAG) pueda depender de el sin
ciclos. La coherencia con `services.json` se comprueba en `validate()` y la fija
un test, no en tiempo de import: un dato de negocio mal escrito no puede tumbar
el bot en produccion, pero si la CI.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

_DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "knowledge_base"
ACTIVITIES_PATH = _DATA_DIR / "activities.json"
SERVICES_PATH = _DATA_DIR / "services.json"

LOCATIONS = ("cartagena", "island")
LANGS = ("es", "en")
_REQUIRED_FIELDS = (
    "id", "family", "cart_type", "services", "requires_certification", "certifies",
    "course_level", "generic", "min_age", "max_age", "label", "for_whom", "sources",
)
_BACKTICKED_ID = re.compile(r"`([a-z0-9_]+)`")


@dataclass(frozen=True)
class Activity:
    id: str
    family: str
    cart_type: str | None
    services: dict[str, tuple[str, ...]]
    requires_certification: bool
    certifies: bool
    course_level: int | None
    generic: bool
    min_age: int | None
    max_age: int | None
    label: dict[str, str]
    for_whom: dict[str, str]
    sources: tuple[str, ...]
    # Id de otra actividad cuyos servicios usa para reservarse y cobrarse (el
    # refresher se vende como el minicurso). No es duena de esos servicios.
    sold_as: str | None = None
    # Glosa corta y MEDIDA para los prompts que extraen datos del cliente
    # (fill_gaps, veto, combinada). Opcional: sin glosa, el valor se enumera solo.
    # Distinta de `for_whom` a proposito -- ver el `_comment` de activities.json.
    gloss: dict[str, str] | None = None
    # Textos para el CLIENTE segun el uso (F3b): `name_in_sentence` ("dudas entre
    # X y Y"), `recall` (con articulo: "me dijiste que querias el curso Open
    # Water"), `price_label`, `plan_label` (plan de grupo por edades) y `pitch`
    # (descripcion corta al comparar). Cada uso tiene su gramatica; por eso no hay
    # un unico nombre.
    texts: dict[str, dict[str, str]] | None = None
    # Para una actividad generica, la concreta que corresponde a quien no tiene
    # certificacion (padi_course -> padi_open_water, regla del owner 2026-09-14).
    default_level: str | None = None

    def all_services(self) -> tuple[str, ...]:
        return tuple(s for loc in LOCATIONS for s in self.services.get(loc, ()))


@dataclass(frozen=True)
class Registry:
    activities: tuple[Activity, ...]
    non_activity_services: dict[str, str]

    def ids(self) -> list[str]:
        return [a.id for a in self.activities]

    def get(self, activity_id: str) -> Activity | None:
        return next((a for a in self.activities if a.id == activity_id), None)


def _parse(raw: dict) -> Registry:
    activities = []
    for entry in raw.get("activities", []):
        missing = [f for f in _REQUIRED_FIELDS if f not in entry]
        if missing:
            raise ValueError(f"activities.json: {entry.get('id', '?')} sin campos {missing}")
        activities.append(Activity(
            id=entry["id"],
            family=entry["family"],
            cart_type=entry["cart_type"],
            services={loc: tuple(entry["services"].get(loc, [])) for loc in LOCATIONS},
            requires_certification=bool(entry["requires_certification"]),
            certifies=bool(entry["certifies"]),
            course_level=entry["course_level"],
            generic=bool(entry["generic"]),
            min_age=entry["min_age"],
            max_age=entry["max_age"],
            label=dict(entry["label"]),
            for_whom=dict(entry["for_whom"]),
            sources=tuple(entry["sources"]),
            sold_as=entry.get("sold_as"),
            gloss=dict(entry["gloss"]) if entry.get("gloss") else None,
            texts={k: dict(v) for k, v in entry["texts"].items()} if entry.get("texts") else None,
            default_level=entry.get("default_level"),
        ))
    return Registry(tuple(activities), dict(raw.get("non_activity_services", {})))


@lru_cache(maxsize=1)
def registry() -> Registry:
    return _parse(json.loads(ACTIVITIES_PATH.read_text(encoding="utf-8-sig")))


def activity_ids() -> list[str]:
    """Todos los ids canonicos, en el orden del fichero."""
    return registry().ids()


def by_id(activity_id: str) -> Activity | None:
    return registry().get(activity_id)


def activity_for_service(service_id: str) -> Activity | None:
    """La actividad a la que pertenece un servicio del catalogo (Cartagena o isla)."""
    return next(
        (a for a in registry().activities if a.sold_as is None and service_id in a.all_services()),
        None,
    )


# Familias de actividades de un dia que el nucleo conversacional cierra con su
# carrito (buceo, iniciacion, snorkel). Los cursos y especialidades tienen su
# propio cierre.
_DAY_FAMILIES = ("dive", "beginner", "snorkel")


def day_activity_ids() -> list[str]:
    """Actividades de un dia con servicios vendibles propios: las que el nucleo
    cierra con su carrito. Sustituye a la lista escrita a mano del nucleo
    (`_ACTIVITY_TO_CART_TYPE`); Bubble Makers queda fuera mientras no tenga
    servicio en el catalogo (discrepancia D2 del plan)."""
    return [
        a.id for a in registry().activities
        if a.family in _DAY_FAMILIES and a.all_services() and a.sold_as is None
    ]


def base_service_id(activity_id: str) -> str | None:
    """Servicio base (desde Cartagena) de una actividad: el que se elige cuando
    se sabe la actividad pero no el plan concreto. None para las genericas."""
    ids = service_ids(activity_id, "cartagena")
    return ids[0] if ids else None


def service_ids(activity_id: str, location: str) -> tuple[str, ...]:
    activity = by_id(activity_id)
    return activity.services.get(location, ()) if activity else ()


def label(activity_id: str, lang: str) -> str:
    activity = by_id(activity_id)
    if activity is None:
        return activity_id
    return activity.label.get(lang) or activity.label["es"]


TEXT_KINDS = ("name_in_sentence", "recall", "price_label", "plan_label", "pitch")


def text(activity_id: str, kind: str, lang: str, default: str | None = None) -> str | None:
    """Texto para el cliente de una actividad segun su uso (ver `Activity.texts`).
    `default` si la actividad no existe o no tiene ese texto."""
    activity = by_id(activity_id)
    variants = (activity.texts or {}).get(kind) if activity else None
    if not variants:
        return default
    return variants.get(lang) or variants.get("es") or default


def resolved_activity_id(activity_id: str) -> str:
    """La actividad concreta que representa a una generica cuando hay que elegir
    un servicio (padi_course -> padi_open_water); la propia si no es generica."""
    activity = by_id(activity_id)
    return activity.default_level if activity and activity.default_level else activity_id


def business_context(lang: str, ids: list[str] | None = None) -> str:
    """Una linea por actividad: "`id` — para quien es". Es el contexto de negocio
    que tienen que ver TODOS los prompts que hablen de actividades, para que ninguno
    decida con menos informacion que otro."""
    wanted = ids if ids is not None else activity_ids()
    lines = []
    for activity_id in wanted:
        activity = by_id(activity_id)
        if activity is None:
            continue
        text = activity.for_whom.get(lang) or activity.for_whom["es"]
        lines.append(f"- `{activity.id}` — {text}")
    return "\n".join(lines)


def validate(services_path: Path = SERVICES_PATH) -> list[str]:
    """Problemas de coherencia del registro contra `services.json`. Lista vacia = OK.

    Comprueba lo que hoy nadie comprueba en las tablas copiadas a mano: que cada
    servicio vendible pertenece a UNA actividad, que no se referencian servicios
    inexistentes, que `requires_certification` coincide con el catalogo y que el
    contexto de negocio no nombra ids que no existen."""
    reg = registry()
    catalog = json.loads(services_path.read_text(encoding="utf-8-sig")).get("services", {})
    problems: list[str] = []

    ids = reg.ids()
    duplicated = sorted({i for i in ids if ids.count(i) > 1})
    if duplicated:
        problems.append(f"ids duplicados: {duplicated}")

    owners: dict[str, list[str]] = {}
    for activity in reg.activities:
        if activity.sold_as is not None:
            target = reg.get(activity.sold_as)
            if target is None:
                problems.append(f"{activity.id}: sold_as apunta a un id inexistente {activity.sold_as!r}")
            elif activity.services != target.services:
                problems.append(f"{activity.id}: sus servicios no coinciden con los de {activity.sold_as}")
        # Una actividad `sold_as` usa servicios ajenos: ni es su duena ni se le
        # exige su `requires_certification` (el refresher es para certificados y
        # se cobra como el minicurso, que no lo es).
        for service_id in (() if activity.sold_as else activity.all_services()):
            owners.setdefault(service_id, []).append(activity.id)
            if service_id not in catalog:
                problems.append(f"{activity.id}: el servicio {service_id!r} no existe en services.json")
                continue
            catalog_cert = bool(catalog[service_id].get("requires_certification", False))
            if catalog_cert != activity.requires_certification:
                problems.append(
                    f"{activity.id}: requires_certification={activity.requires_certification} "
                    f"pero {service_id} dice {catalog_cert} en services.json"
                )
        for service_id in activity.services.get("island", ()):
            if not service_id.endswith("_already_on_island"):
                problems.append(f"{activity.id}: {service_id!r} esta en 'island' sin ser variante de isla")
        if activity.generic and activity.all_services():
            problems.append(f"{activity.id}: una actividad generica no puede tener servicios")
        if activity.default_level is not None and reg.get(activity.default_level) is None:
            problems.append(f"{activity.id}: default_level apunta a un id inexistente {activity.default_level!r}")
        for kind, variants in (activity.texts or {}).items():
            if kind not in TEXT_KINDS:
                problems.append(f"{activity.id}: texts.{kind} no es un uso conocido {TEXT_KINDS}")
            for lang in LANGS:
                if not variants.get(lang):
                    problems.append(f"{activity.id}: texts.{kind} sin {lang}")
        for lang in LANGS:
            if activity.gloss is not None and not activity.gloss.get(lang):
                problems.append(f"{activity.id}: gloss sin {lang}")
            if not activity.label.get(lang):
                problems.append(f"{activity.id}: falta label.{lang}")
            if not activity.for_whom.get(lang):
                problems.append(f"{activity.id}: falta for_whom.{lang}")
            for named in _BACKTICKED_ID.findall(activity.for_whom.get(lang, "")):
                if named not in ids:
                    problems.append(f"{activity.id}: for_whom.{lang} nombra un id inexistente {named!r}")

    for service_id, activity_ids_ in owners.items():
        if len(activity_ids_) > 1:
            problems.append(f"{service_id} pertenece a varias actividades: {activity_ids_}")
    for service_id in catalog:
        if service_id not in owners and service_id not in reg.non_activity_services:
            problems.append(f"{service_id} (services.json) no pertenece a ninguna actividad")
    for service_id in reg.non_activity_services:
        if service_id not in catalog:
            problems.append(f"non_activity_services: {service_id!r} no existe en services.json")
    return problems
