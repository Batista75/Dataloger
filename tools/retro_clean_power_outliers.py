from __future__ import annotations

import argparse
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

CHANNELS = ("a1", "b1", "c1", "a2", "b2", "c2")
POWER_MIN_W = -6000.0
POWER_MAX_W = 9000.0


@dataclass
class Row:
    row_id: int
    ts: datetime
    values: dict[str, float]


def parse_ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def create_backup(db_path: Path) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup = db_path.with_suffix(db_path.suffix + f".bak_bounds_{stamp}")
    with sqlite3.connect(db_path) as src, sqlite3.connect(backup) as dst:
        src.backup(dst)
    return backup


def load_rows(conn: sqlite3.Connection, since_ts: str | None) -> list[Row]:
    query = """
        SELECT id, ts_utc,
               a1_production_kwh, a1_consumption_kwh,
               b1_production_kwh, b1_consumption_kwh,
               c1_production_kwh, c1_consumption_kwh,
               a2_production_kwh, a2_consumption_kwh,
               b2_production_kwh, b2_consumption_kwh,
               c2_production_kwh, c2_consumption_kwh
        FROM measurements
    """
    params: tuple[object, ...] = ()
    if since_ts:
        query += " WHERE ts_utc >= ?"
        params = (since_ts,)
    query += " ORDER BY ts_utc ASC, id ASC"

    rows = conn.execute(query, params).fetchall()
    result: list[Row] = []
    for r in rows:
        values: dict[str, float] = {}
        for ch in CHANNELS:
            values[f"{ch}_production_kwh"] = float(r[f"{ch}_production_kwh"] or 0.0)
            values[f"{ch}_consumption_kwh"] = float(r[f"{ch}_consumption_kwh"] or 0.0)
        result.append(Row(row_id=int(r["id"]), ts=parse_ts(str(r["ts_utc"])), values=values))
    return result


def clean_rows(rows: list[Row]) -> tuple[int, dict[str, int]]:
    if len(rows) < 2:
        return 0, {ch: 0 for ch in CHANNELS}

    fixed_rows = 0
    fixed_by_channel = {ch: 0 for ch in CHANNELS}

    for i in range(1, len(rows)):
        prev = rows[i - 1]
        cur = rows[i]
        dt = (cur.ts - prev.ts).total_seconds()
        if dt <= 0:
            continue

        changed = False

        for ch in CHANNELS:
            prev_prod = prev.values[f"{ch}_production_kwh"]
            prev_cons = prev.values[f"{ch}_consumption_kwh"]
            cur_prod = cur.values[f"{ch}_production_kwh"]
            cur_cons = cur.values[f"{ch}_consumption_kwh"]

            delta_signed_kwh = (cur_cons - prev_cons) - (cur_prod - prev_prod)
            signed_power_w = (delta_signed_kwh * 3600000.0) / dt

            if signed_power_w < POWER_MIN_W or signed_power_w > POWER_MAX_W:
                cur.values[f"{ch}_production_kwh"] = prev_prod
                cur.values[f"{ch}_consumption_kwh"] = prev_cons
                fixed_by_channel[ch] += 1
                changed = True

        if changed:
            fixed_rows += 1

    return fixed_rows, fixed_by_channel


def write_rows(conn: sqlite3.Connection, rows: list[Row]) -> None:
    updates = []
    for r in rows:
        totals_prod = sum(r.values[f"{ch}_production_kwh"] for ch in CHANNELS)
        totals_cons = sum(r.values[f"{ch}_consumption_kwh"] for ch in CHANNELS)
        updates.append(
            (
                round(r.values["a1_production_kwh"], 6),
                round(r.values["a1_consumption_kwh"], 6),
                round(r.values["b1_production_kwh"], 6),
                round(r.values["b1_consumption_kwh"], 6),
                round(r.values["c1_production_kwh"], 6),
                round(r.values["c1_consumption_kwh"], 6),
                round(r.values["a2_production_kwh"], 6),
                round(r.values["a2_consumption_kwh"], 6),
                round(r.values["b2_production_kwh"], 6),
                round(r.values["b2_consumption_kwh"], 6),
                round(r.values["c2_production_kwh"], 6),
                round(r.values["c2_consumption_kwh"], 6),
                round(totals_prod, 6),
                round(totals_cons, 6),
                r.row_id,
            )
        )

    conn.executemany(
        """
        UPDATE measurements
        SET a1_production_kwh = ?, a1_consumption_kwh = ?,
            b1_production_kwh = ?, b1_consumption_kwh = ?,
            c1_production_kwh = ?, c1_consumption_kwh = ?,
            a2_production_kwh = ?, a2_consumption_kwh = ?,
            b2_production_kwh = ?, b2_consumption_kwh = ?,
            c2_production_kwh = ?, c2_consumption_kwh = ?,
            total_production_kwh = ?, total_consumption_kwh = ?
        WHERE id = ?
        """,
        updates,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Retro-clean out-of-range power points by replacing with previous values.")
    parser.add_argument("--db", required=True, help="Path to sqlite DB")
    parser.add_argument("--since-ts", default=None, help="Optional UTC ISO ts lower bound")
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        raise FileNotFoundError(f"DB not found: {db_path}")

    backup = create_backup(db_path)

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = load_rows(conn, args.since_ts)
        fixed_rows, fixed_by_channel = clean_rows(rows)
        write_rows(conn, rows)
        conn.commit()

    print(f"Backup: {backup}")
    print(f"Rows scanned: {len(rows)}")
    print(f"Rows fixed: {fixed_rows}")
    print(
        "Fixed by channel: "
        + ", ".join(f"{ch}={fixed_by_channel[ch]}" for ch in CHANNELS)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
