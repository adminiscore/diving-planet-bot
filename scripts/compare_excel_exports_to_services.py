import argparse
import json
from pathlib import Path
from typing import Any


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _norm(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        return None


def _load_roverd_table(export_path: Path) -> dict[str, tuple[float | None, float | None, float | None, float | None]]:
    raw = json.loads(export_path.read_text(encoding="utf-8"))
    sheets = {s["name"]: s for s in raw.get("sheets", [])}
    roverd = sheets.get("ROVERD")
    if not roverd:
        raise SystemExit("ROVERD sheet not found in export")

    table: dict[str, tuple[float | None, float | None, float | None, float | None]] = {}
    for row in roverd.get("grid", []):
        if len(row) < 6:
            continue
        label = (row[1] or "").strip()
        if not label or label == "PRICES 2026":
            continue

        normal_cart = _to_float(row[2])
        online_cart = _to_float(row[3])
        normal_isla = _to_float(row[4])
        online_isla = _to_float(row[5])

        if any(v is not None for v in (normal_cart, online_cart, normal_isla, online_isla)):
            table[label] = (normal_cart, online_cart, normal_isla, online_isla)

    return table


def main() -> int:
    parser = argparse.ArgumentParser(prog="compare_excel_exports_to_services")
    parser.add_argument(
        "--services",
        type=str,
        default="data/knowledge_base/services.json",
    )
    parser.add_argument(
        "--tarifa-export",
        type=str,
        default="data/excel_exports/TARIFA 2026 UNO POR UNO.json",
    )
    args = parser.parse_args()

    services_path = Path(args.services)
    export_path = Path(args.tarifa_export)

    services = json.loads(services_path.read_text(encoding="utf-8")).get("services", {})
    roverd = _load_roverd_table(export_path)

    mapping: dict[str, tuple[str, str]] = {
        "2_dives_1_day": ("Fun Dives", "cartagena"),
        "2_dives_1_day_already_on_island": ("Fun Dives", "isla"),
        "minicourse": ("Mini Course", "cartagena"),
        "minicourse_already_on_island": ("Mini Course", "isla"),
        "snorkeling": ("Snorkeling", "cartagena"),
        "snorkeling_already_on_island": ("Snorkeling", "isla"),
        "open_water": ("Basic Course", "cartagena"),
        "open_water_already_on_island": ("Basic Course", "isla"),
        "advanced": ("Advance Course", "cartagena"),
        "advanced_already_on_island": ("Advance Course", "isla"),
        "referral": ("Referral / MINDFUL", "cartagena"),
        "mindful_diving": ("Mindful Diving", "cartagena"),
        "rescue": ("Rescue Course", "cartagena"),
        "5_dives_2_days": ("Package 5", "cartagena"),
        "5_dives_2_days_already_on_island": ("Package 5", "isla"),
        "7_dives_3_days": ("Package 7", "cartagena"),
        "7_dives_3_days_already_on_island": ("Package 7", "isla"),
        "9_dives_4_days": ("Package 9", "cartagena"),
        "naturalist_specialty": ("Naturalist", "cartagena"),
        "fish_identification_specialty": ("Fish ID", "cartagena"),
        "buoyancy_specialty": ("Bouyancy", "cartagena"),
        "nitrox_specialty": ("Nitrox", "cartagena"),
        "naturalist_specialty_already_on_island": ("Naturalist", "isla"),
        "fish_identification_specialty_already_on_island": ("Fish ID", "isla"),
        "buoyancy_specialty_already_on_island": ("Bouyancy", "isla"),
        "nitrox_specialty_already_on_island": ("Nitrox", "isla"),
    }

    diffs: list[str] = []
    missing_in_services: list[str] = []
    missing_in_roverd: list[str] = []

    for service_id, (label, where) in mapping.items():
        if service_id not in services:
            missing_in_services.append(service_id)
            continue

        row = roverd.get(label)
        if not row:
            missing_in_roverd.append(f"{service_id} ({label}/{where})")
            continue

        normal_cart, online_cart, normal_isla, online_isla = row
        expected_online = online_cart if where == "cartagena" else online_isla
        expected_normal = normal_cart if where == "cartagena" else normal_isla

        cur_online = _norm(services[service_id].get("price_usd"))
        cur_normal = _norm(services[service_id].get("price_usd_normal"))

        if cur_online != expected_online or cur_normal != expected_normal:
            diffs.append(
                f"{service_id} [{where}] {label}: {cur_online}/{cur_normal} -> {expected_online}/{expected_normal}"
            )

    print(f"services.json: {services_path}")
    print(f"tarifa export: {export_path}")

    if missing_in_services:
        print("\nMissing in services.json:")
        for sid in missing_in_services:
            print("-", sid)

    if missing_in_roverd:
        print("\nMissing in ROVERD table:")
        for item in missing_in_roverd:
            print("-", item)

    print("\nPrice diffs:")
    if diffs:
        for d in diffs:
            print("-", d)
    else:
        print("- (none)")

    covered_labels = {label for (label, _) in mapping.values()}
    extra_labels = sorted(set(roverd) - covered_labels)
    if extra_labels:
        print("\nROVERD labels not mapped:")
        for lab in extra_labels:
            print("-", lab)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
