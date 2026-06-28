from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

CHANNELS = ("a1", "b1", "c1", "a2", "b2", "c2")

# Refoss export shows production as negative on grid / generator channels.
NEGATIVE_PRODUCTION_CHANNELS = frozenset({"c1", "a2"})

# quality_flag=2 rows come from tools/import_em06_history_csv.py (daily totals, not cumulative).
IMPORTED_QUALITY_FLAGS = frozenset({2})

HEADER_COLUMNS = [
    "Date",
    "Channel A1 Production(kWh)",
    "Channel A1 Consumption(kWh)",
    "Channel B1 Production(kWh)",
    "Channel B1 Consumption(kWh)",
    "Channel C1 Production(kWh)",
    "Channel C1 Consumption(kWh)",
    "Channel A2 Production(kWh)",
    "Channel A2 Consumption(kWh)",
    "Channel B2 Production(kWh)",
    "Channel B2 Consumption(kWh)",
    "Channel C2 Production(kWh)",
    "Channel C2 Consumption(kWh)",
]

HEADER_MAP = {
    "Date": "date",
    "\ufeffDate": "date",
    "Channel A1 Production(kWh)": "a1_prod",
    "Channel A1 Consumption(kWh)": "a1_cons",
    "Channel B1 Production(kWh)": "b1_prod",
    "Channel B1 Consumption(kWh)": "b1_cons",
    "Channel C1 Production(kWh)": "c1_prod",
    "Channel C1 Consumption(kWh)": "c1_cons",
    "Channel A2 Production(kWh)": "a2_prod",
    "Channel A2 Consumption(kWh)": "a2_cons",
    "Channel B2 Production(kWh)": "b2_prod",
    "Channel B2 Consumption(kWh)": "b2_cons",
    "Channel C2 Production(kWh)": "c2_prod",
    "Channel C2 Consumption(kWh)": "c2_cons",
}


@dataclass
class DailyRow:
    date_iso: str
    a1_production_kwh: float
    a1_consumption_kwh: float
    b1_production_kwh: float
    b1_consumption_kwh: float
    c1_production_kwh: float
    c1_consumption_kwh: float
    a2_production_kwh: float
    a2_consumption_kwh: float
    b2_production_kwh: float
    b2_consumption_kwh: float
    c2_production_kwh: float
    c2_consumption_kwh: float

    def get_production(self, channel: str) -> float:
        return float(getattr(self, f"{channel}_production_kwh"))

    def get_consumption(self, channel: str) -> float:
        return float(getattr(self, f"{channel}_consumption_kwh"))


def _normalize_header_name(name: str) -> str:
    return name.strip().lstrip("\ufeff")


def _normalize_line(line: str) -> list[str]:
    cleaned = line.replace("\t,", ",").replace(",\t", ",").replace("\t", "")
    parts = [part.strip() for part in cleaned.split(",")]
    while parts and parts[-1] == "":
        parts.pop()
    return parts


def _to_float(raw: str) -> float:
    value = raw.strip().replace(" ", "")
    if not value:
        return 0.0
    try:
        return float(value)
    except ValueError:
        return 0.0


def _abs_non_negative(value: float) -> float:
    return round(abs(value), 6)


def parse_csv_rows(csv_path: Path) -> list[DailyRow]:
    lines = csv_path.read_text(encoding="utf-8", errors="replace").splitlines()
    if not lines:
        return []

    header_parts = _normalize_line(lines[0])
    if len(header_parts) < 13:
        raise ValueError("CSV header format is not recognized")

    idx: dict[str, int] = {}
    for i, raw in enumerate(header_parts):
        mapped = HEADER_MAP.get(_normalize_header_name(raw))
        if mapped:
            idx[mapped] = i

    required = [
        "date",
        "a1_prod",
        "a1_cons",
        "b1_prod",
        "b1_cons",
        "c1_prod",
        "c1_cons",
        "a2_prod",
        "a2_cons",
        "b2_prod",
        "b2_cons",
        "c2_prod",
        "c2_cons",
    ]
    missing = [key for key in required if key not in idx]
    if missing:
        raise ValueError(f"CSV missing expected columns: {missing}")

    rows: list[DailyRow] = []
    for raw_line in lines[1:]:
        if not raw_line.strip():
            continue
        parts = _normalize_line(raw_line)
        if len(parts) <= idx["c2_cons"]:
            continue

        date_iso = parts[idx["date"]]
        if not date_iso:
            continue

        rows.append(
            DailyRow(
                date_iso=date_iso,
                a1_production_kwh=_abs_non_negative(_to_float(parts[idx["a1_prod"]])),
                a1_consumption_kwh=_abs_non_negative(_to_float(parts[idx["a1_cons"]])),
                b1_production_kwh=_abs_non_negative(_to_float(parts[idx["b1_prod"]])),
                b1_consumption_kwh=_abs_non_negative(_to_float(parts[idx["b1_cons"]])),
                c1_production_kwh=_abs_non_negative(_to_float(parts[idx["c1_prod"]])),
                c1_consumption_kwh=_abs_non_negative(_to_float(parts[idx["c1_cons"]])),
                a2_production_kwh=_abs_non_negative(_to_float(parts[idx["a2_prod"]])),
                a2_consumption_kwh=_abs_non_negative(_to_float(parts[idx["a2_cons"]])),
                b2_production_kwh=_abs_non_negative(_to_float(parts[idx["b2_prod"]])),
                b2_consumption_kwh=_abs_non_negative(_to_float(parts[idx["b2_cons"]])),
                c2_production_kwh=_abs_non_negative(_to_float(parts[idx["c2_prod"]])),
                c2_consumption_kwh=_abs_non_negative(_to_float(parts[idx["c2_cons"]])),
            )
        )

    return rows


def _format_production(channel: str, daily_kwh: float) -> str:
    value = max(float(daily_kwh), 0.0)
    if value <= 0.0:
        return "0.000"
    if channel in NEGATIVE_PRODUCTION_CHANNELS:
        return f"{-value:.3f}"
    return f"{value:.3f}"


def _format_consumption(daily_kwh: float) -> str:
    return f"{max(float(daily_kwh), 0.0):.3f}"


def format_header_line() -> str:
    return "\t,".join(HEADER_COLUMNS) + "\t,"


def format_data_line(row: DailyRow) -> str:
    values = [row.date_iso]
    for channel in CHANNELS:
        values.append(_format_production(channel, row.get_production(channel)))
        values.append(_format_consumption(row.get_consumption(channel)))
    return "\t,".join(values) + "\t,"


def write_csv(rows: list[DailyRow], csv_path: Path) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [format_header_line(), *[format_data_line(row) for row in rows]]
    csv_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def merge_daily_rows(
    base_rows: list[DailyRow],
    extension_rows: list[DailyRow],
    prefer: str = "extension",
) -> list[DailyRow]:
    merged: dict[str, DailyRow] = {row.date_iso: row for row in base_rows}
    for row in extension_rows:
        if prefer == "extension" or row.date_iso not in merged:
            merged[row.date_iso] = row
    return [merged[date_iso] for date_iso in sorted(merged.keys())]


def today_utc_iso() -> str:
    return datetime.now(timezone.utc).date().isoformat()
