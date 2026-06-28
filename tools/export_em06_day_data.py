from __future__ import annotations

import argparse
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.em06_day_data_io import (  # noqa: E402
    CHANNELS,
    IMPORTED_QUALITY_FLAGS,
    DailyRow,
    merge_daily_rows,
    parse_csv_rows,
    today_utc_iso,
    write_csv,
)


@dataclass
class MeasurementSnapshot:
    day_iso: str
    ts_utc: str
    row_id: int
    quality_flag: int
    values: dict[str, tuple[float, float]]


def _channel_values(row: sqlite3.Row) -> dict[str, tuple[float, float]]:
    values: dict[str, tuple[float, float]] = {}
    for channel in CHANNELS:
        production = max(float(row[f"{channel}_production_kwh"] or 0.0), 0.0)
        consumption = max(float(row[f"{channel}_consumption_kwh"] or 0.0), 0.0)
        values[channel] = (production, consumption)
    return values


def _load_snapshots(db_path: Path) -> list[MeasurementSnapshot]:
    query = """
    SELECT id, ts_utc, quality_flag,
        a1_production_kwh, a1_consumption_kwh,
        b1_production_kwh, b1_consumption_kwh,
        c1_production_kwh, c1_consumption_kwh,
        a2_production_kwh, a2_consumption_kwh,
        b2_production_kwh, b2_consumption_kwh,
        c2_production_kwh, c2_consumption_kwh
    FROM measurements
    ORDER BY ts_utc ASC, id ASC
    """
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(query).fetchall()

    snapshots: list[MeasurementSnapshot] = []
    for row in rows:
        ts_utc = str(row["ts_utc"])
        snapshots.append(
            MeasurementSnapshot(
                day_iso=ts_utc[:10],
                ts_utc=ts_utc,
                row_id=int(row["id"]),
                quality_flag=int(row["quality_flag"] or 0),
                values=_channel_values(row),
            )
        )
    return snapshots


def _is_imported_daily_snapshot(day_rows: list[MeasurementSnapshot]) -> bool:
    imported_rows = [row for row in day_rows if row.quality_flag in IMPORTED_QUALITY_FLAGS]
    live_rows = [row for row in day_rows if row.quality_flag not in IMPORTED_QUALITY_FLAGS]
    if not imported_rows or live_rows:
        return False
    return len(imported_rows) == 1


def _delta_from_snapshots(
    current: dict[str, tuple[float, float]],
    previous: dict[str, tuple[float, float]] | None,
) -> dict[str, tuple[float, float]]:
    daily: dict[str, tuple[float, float]] = {}
    for channel in CHANNELS:
        cur_prod, cur_cons = current[channel]
        if previous is None:
            daily[channel] = (cur_prod, cur_cons)
            continue
        prev_prod, prev_cons = previous[channel]
        daily[channel] = (
            max(cur_prod - prev_prod, 0.0),
            max(cur_cons - prev_cons, 0.0),
        )
    return daily


def _daily_row_from_values(day_iso: str, daily_values: dict[str, tuple[float, float]]) -> DailyRow:
    return DailyRow(
        date_iso=day_iso,
        a1_production_kwh=daily_values["a1"][0],
        a1_consumption_kwh=daily_values["a1"][1],
        b1_production_kwh=daily_values["b1"][0],
        b1_consumption_kwh=daily_values["b1"][1],
        c1_production_kwh=daily_values["c1"][0],
        c1_consumption_kwh=daily_values["c1"][1],
        a2_production_kwh=daily_values["a2"][0],
        a2_consumption_kwh=daily_values["a2"][1],
        b2_production_kwh=daily_values["b2"][0],
        b2_consumption_kwh=daily_values["b2"][1],
        c2_production_kwh=daily_values["c2"][0],
        c2_consumption_kwh=daily_values["c2"][1],
    )


def build_daily_rows(
    snapshots: list[MeasurementSnapshot],
    from_date: str | None = None,
    to_date: str | None = None,
    exclude_today: bool = True,
) -> list[DailyRow]:
    if not snapshots:
        return []

    grouped: dict[str, list[MeasurementSnapshot]] = {}
    for snapshot in snapshots:
        grouped.setdefault(snapshot.day_iso, []).append(snapshot)

    daily_rows: list[DailyRow] = []
    previous_end_values: dict[str, tuple[float, float]] | None = None
    today = today_utc_iso()

    for day_iso in sorted(grouped.keys()):
        if exclude_today and day_iso == today:
            continue
        if from_date and day_iso < from_date:
            previous_end_values = grouped[day_iso][-1].values
            continue
        if to_date and day_iso > to_date:
            continue

        day_rows = grouped[day_iso]
        if _is_imported_daily_snapshot(day_rows):
            daily_values = {
                channel: (production, consumption)
                for channel, (production, consumption) in day_rows[-1].values.items()
            }
        else:
            live_rows = [row for row in day_rows if row.quality_flag not in IMPORTED_QUALITY_FLAGS]
            if not live_rows:
                live_rows = day_rows
            end_values = live_rows[-1].values
            daily_values = _delta_from_snapshots(end_values, previous_end_values)

        daily_rows.append(_daily_row_from_values(day_iso, daily_values))
        previous_end_values = day_rows[-1].values

    return daily_rows


def default_output_name() -> str:
    stamp = today_utc_iso().replace("-", "")
    return f"Power Monitor Day Data - Smart Energy Monitor - {stamp}.csv"


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Export Raspberry/SQLite measurements as Refoss Power Monitor Day Data CSV "
            "(same format as the mobile app export)."
        )
    )
    parser.add_argument("--db", default="data/measurements.db", help="Path to SQLite DB")
    parser.add_argument(
        "--out",
        default=f"exports/{default_output_name()}",
        help="Output CSV path (Refoss-compatible format)",
    )
    parser.add_argument("--from-date", help="Include days from YYYY-MM-DD (UTC day)")
    parser.add_argument("--to-date", help="Include days up to YYYY-MM-DD (UTC day)")
    parser.add_argument(
        "--include-today",
        action="store_true",
        help="Include the current UTC day (partial day)",
    )
    parser.add_argument(
        "--merge-with",
        help="Existing Refoss history CSV to merge with (extension wins on duplicate dates)",
    )
    parser.add_argument(
        "--merge-out",
        help="Output path for merged CSV (default: same folder as --out with _combined suffix)",
    )
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"DB_NOT_FOUND={db_path}")
        return 1

    snapshots = _load_snapshots(db_path)
    extension_rows = build_daily_rows(
        snapshots,
        from_date=args.from_date,
        to_date=args.to_date,
        exclude_today=not args.include_today,
    )
    if not extension_rows:
        print("DAILY_ROWS=0")
        return 0

    out_path = Path(args.out)
    write_csv(extension_rows, out_path)
    print(f"DAILY_ROWS={len(extension_rows)}")
    print(f"FIRST_DAY={extension_rows[0].date_iso}")
    print(f"LAST_DAY={extension_rows[-1].date_iso}")
    print(f"OUTPUT={out_path}")

    if args.merge_with:
        base_path = Path(args.merge_with)
        if not base_path.exists():
            print(f"MERGE_BASE_NOT_FOUND={base_path}")
            return 1
        base_rows = parse_csv_rows(base_path)
        merged_rows = merge_daily_rows(base_rows, extension_rows, prefer="extension")
        merge_out = Path(args.merge_out) if args.merge_out else out_path.with_name(out_path.stem + "_combined.csv")
        write_csv(merged_rows, merge_out)
        print(f"MERGED_ROWS={len(merged_rows)}")
        print(f"MERGED_OUTPUT={merge_out}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
