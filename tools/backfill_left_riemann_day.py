from __future__ import annotations

import sqlite3
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


CHANNELS = ("a1", "b1", "c1", "a2", "b2", "c2")


@dataclass
class RowData:
    row_id: int
    ts_utc: datetime
    signed_power_w: dict[str, float]


def parse_ts_utc(ts_value: str) -> datetime:
    return datetime.fromisoformat(ts_value.replace("Z", "+00:00")).astimezone(timezone.utc)


def read_rows(conn: sqlite3.Connection) -> list[RowData]:
    rows = conn.execute(
        """
        SELECT id, ts_utc,
            a1_production_kwh, a1_consumption_kwh,
            b1_production_kwh, b1_consumption_kwh,
            c1_production_kwh, c1_consumption_kwh,
            a2_production_kwh, a2_consumption_kwh,
            b2_production_kwh, b2_consumption_kwh,
            c2_production_kwh, c2_consumption_kwh
        FROM measurements
        ORDER BY ts_utc ASC, id ASC
        """
    ).fetchall()

    result: list[RowData] = []
    for row in rows:
        signed: dict[str, float] = {}
        for channel in CHANNELS:
            prod = max(float(row[f"{channel}_production_kwh"] or 0.0), 0.0)
            cons = max(float(row[f"{channel}_consumption_kwh"] or 0.0), 0.0)
            net = cons - prod
            if abs(net) <= 40.0:
                net *= 1000.0
            signed[channel] = net
        result.append(RowData(row_id=int(row["id"]), ts_utc=parse_ts_utc(str(row["ts_utc"])), signed_power_w=signed))
    return result


def backfill_day(db_path: Path, since_ts_utc: datetime) -> int:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = read_rows(conn)
        if not rows:
            return 0

        consumption_idx = {channel: 0.0 for channel in CHANNELS}
        production_idx = {channel: 0.0 for channel in CHANNELS}

        updates: list[tuple[float, ...]] = []
        previous: RowData | None = None

        for current in rows:
            if previous is not None:
                dt_seconds = (current.ts_utc - previous.ts_utc).total_seconds()
                if 0.0 < dt_seconds <= 900.0:
                    for channel in CHANNELS:
                        prev_power = previous.signed_power_w[channel]
                        delta_kwh = abs(prev_power) * dt_seconds / 3600000.0
                        if prev_power >= 0.0:
                            consumption_idx[channel] += delta_kwh
                        else:
                            production_idx[channel] += delta_kwh

            if current.ts_utc >= since_ts_utc:
                total_prod = sum(production_idx.values())
                total_cons = sum(consumption_idx.values())
                updates.append(
                    (
                        round(production_idx["a1"], 6),
                        round(consumption_idx["a1"], 6),
                        round(production_idx["b1"], 6),
                        round(consumption_idx["b1"], 6),
                        round(production_idx["c1"], 6),
                        round(consumption_idx["c1"], 6),
                        round(production_idx["a2"], 6),
                        round(consumption_idx["a2"], 6),
                        round(production_idx["b2"], 6),
                        round(consumption_idx["b2"], 6),
                        round(production_idx["c2"], 6),
                        round(consumption_idx["c2"], 6),
                        round(total_prod, 6),
                        round(total_cons, 6),
                        current.row_id,
                    )
                )

            previous = current

        if not updates:
            return 0

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
        conn.commit()
        return len(updates)


def main() -> int:
    if len(sys.argv) != 3:
        print("Usage: python tools/backfill_left_riemann_day.py <db_path> <since_ts_utc>")
        print("Example: python tools/backfill_left_riemann_day.py data/measurements.db 2026-06-21T00:00:00+00:00")
        return 1

    db_path = Path(sys.argv[1])
    since_ts_utc = parse_ts_utc(sys.argv[2])
    count = backfill_day(db_path, since_ts_utc)
    print(f"Backfill updated rows: {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())