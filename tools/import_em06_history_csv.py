from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.em06_day_data_io import DailyRow, parse_csv_rows


def _iter_insert_values(rows: Iterable[DailyRow], include_today: bool) -> list[tuple[object, ...]]:
    today = datetime.now(timezone.utc).date().isoformat()
    values: list[tuple[object, ...]] = []

    for row in rows:
        if not include_today and row.date_iso == today:
            continue

        ts_utc = f"{row.date_iso}T23:55:00+00:00"
        total_prod = round(
            row.a1_production_kwh
            + row.b1_production_kwh
            + row.c1_production_kwh
            + row.a2_production_kwh
            + row.b2_production_kwh
            + row.c2_production_kwh,
            6,
        )
        total_cons = round(
            row.a1_consumption_kwh
            + row.b1_consumption_kwh
            + row.c1_consumption_kwh
            + row.a2_consumption_kwh
            + row.b2_consumption_kwh
            + row.c2_consumption_kwh,
            6,
        )

        values.append(
            (
                ts_utc,
                row.a1_production_kwh,
                row.a1_consumption_kwh,
                row.b1_production_kwh,
                row.b1_consumption_kwh,
                row.c1_production_kwh,
                row.c1_consumption_kwh,
                row.a2_production_kwh,
                row.a2_consumption_kwh,
                row.b2_production_kwh,
                row.b2_consumption_kwh,
                row.c2_production_kwh,
                row.c2_consumption_kwh,
                total_prod,
                total_cons,
                None,
                None,
                None,
                2,
            )
        )

    return values


def import_history(csv_path: Path, db_path: Path, include_today: bool) -> int:
    rows = parse_csv_rows(csv_path)
    values = _iter_insert_values(rows, include_today=include_today)
    if not values:
        return 0

    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        for item in values:
            conn.execute("DELETE FROM measurements WHERE ts_utc = ?", (item[0],))
        conn.executemany(
            """
            INSERT INTO measurements (
                ts_utc,
                a1_production_kwh, a1_consumption_kwh,
                b1_production_kwh, b1_consumption_kwh,
                c1_production_kwh, c1_consumption_kwh,
                a2_production_kwh, a2_consumption_kwh,
                b2_production_kwh, b2_consumption_kwh,
                c2_production_kwh, c2_consumption_kwh,
                total_production_kwh, total_consumption_kwh,
                voltage_v, frequency_hz, power_factor, quality_flag
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            values,
        )
        conn.commit()

    return len(values)


def fix_inverted_rows(db_path: Path, date_iso: str) -> int:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT id,
                   a1_production_kwh, a1_consumption_kwh,
                   b1_production_kwh, b1_consumption_kwh,
                   c1_production_kwh, c1_consumption_kwh,
                   a2_production_kwh, a2_consumption_kwh,
                   b2_production_kwh, b2_consumption_kwh,
                   c2_production_kwh, c2_consumption_kwh
            FROM measurements
            WHERE substr(ts_utc, 1, 10) = ?
              AND (
                    a2_consumption_kwh > a2_production_kwh
                 OR b2_production_kwh > b2_consumption_kwh
                 OR c2_production_kwh > c2_consumption_kwh
              )
            ORDER BY id ASC
            """,
            (date_iso,),
        ).fetchall()

        updates: list[tuple[float, ...]] = []
        for row in rows:
            a2_prod = float(row["a2_production_kwh"] or 0.0)
            a2_cons = float(row["a2_consumption_kwh"] or 0.0)
            b2_prod = float(row["b2_production_kwh"] or 0.0)
            b2_cons = float(row["b2_consumption_kwh"] or 0.0)
            c2_prod = float(row["c2_production_kwh"] or 0.0)
            c2_cons = float(row["c2_consumption_kwh"] or 0.0)

            new_a2_prod, new_a2_cons = a2_cons, a2_prod
            new_b2_prod, new_b2_cons = b2_cons, b2_prod
            new_c2_prod, new_c2_cons = c2_cons, c2_prod

            total_prod = (
                float(row["a1_production_kwh"] or 0.0)
                + float(row["b1_production_kwh"] or 0.0)
                + float(row["c1_production_kwh"] or 0.0)
                + new_a2_prod
                + new_b2_prod
                + new_c2_prod
            )
            total_cons = (
                float(row["a1_consumption_kwh"] or 0.0)
                + float(row["b1_consumption_kwh"] or 0.0)
                + float(row["c1_consumption_kwh"] or 0.0)
                + new_a2_cons
                + new_b2_cons
                + new_c2_cons
            )

            updates.append(
                (
                    round(new_a2_prod, 6),
                    round(new_a2_cons, 6),
                    round(new_b2_prod, 6),
                    round(new_b2_cons, 6),
                    round(new_c2_prod, 6),
                    round(new_c2_cons, 6),
                    round(total_prod, 6),
                    round(total_cons, 6),
                    int(row["id"]),
                )
            )

        if updates:
            conn.executemany(
                """
                UPDATE measurements
                SET a2_production_kwh = ?, a2_consumption_kwh = ?,
                    b2_production_kwh = ?, b2_consumption_kwh = ?,
                    c2_production_kwh = ?, c2_consumption_kwh = ?,
                    total_production_kwh = ?, total_consumption_kwh = ?
                WHERE id = ?
                """,
                updates,
            )
            conn.commit()

    return len(updates)


def create_backup(db_path: Path) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_path = db_path.with_suffix(db_path.suffix + f".bak_{stamp}")
    with sqlite3.connect(db_path) as source, sqlite3.connect(backup_path) as backup:
        source.backup(backup)
    return backup_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Import EM06 daily history CSV into measurements DB and fix inverted A2/B2/C2 rows.")
    parser.add_argument("--csv", required=True, help="Path to export CSV")
    parser.add_argument("--db", required=True, help="Path to SQLite DB")
    parser.add_argument("--fix-date", default=datetime.now(timezone.utc).date().isoformat(), help="UTC date (YYYY-MM-DD) for inversion correction")
    parser.add_argument("--include-today", action="store_true", help="Also import today's daily row from CSV")
    args = parser.parse_args()

    csv_path = Path(args.csv)
    db_path = Path(args.db)

    if not csv_path.exists():
        raise FileNotFoundError(f"CSV not found: {csv_path}")
    if not db_path.exists():
        raise FileNotFoundError(f"DB not found: {db_path}")

    backup_path = create_backup(db_path)
    imported = import_history(csv_path, db_path, include_today=args.include_today)
    fixed = fix_inverted_rows(db_path, args.fix_date)

    print(f"Backup: {backup_path}")
    print(f"Imported daily rows: {imported}")
    print(f"Fixed inverted rows ({args.fix_date}): {fixed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
