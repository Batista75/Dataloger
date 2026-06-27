from __future__ import annotations

import argparse
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

from src.core.config import settings
from src.db.init_db import init_database


def backup_database(db_path: Path) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = db_path.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_path = backup_dir / f"{db_path.stem}_backup_{timestamp}{db_path.suffix}"
    shutil.copy2(db_path, backup_path)
    return backup_path


def count_rows(conn: sqlite3.Connection, table: str) -> int:
    cur = conn.execute(f"SELECT COUNT(*) FROM {table}")
    row = cur.fetchone()
    return int(row[0]) if row else 0


def purge_history(db_path: Path, include_events: bool) -> dict[str, int]:
    deleted: dict[str, int] = {}

    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA foreign_keys = ON")

        measurements_before = count_rows(conn, "measurements")
        conn.execute("DELETE FROM measurements")
        conn.execute("DELETE FROM sqlite_sequence WHERE name='measurements'")
        deleted["measurements"] = measurements_before

        if include_events:
            events_before = count_rows(conn, "system_events")
            conn.execute("DELETE FROM system_events")
            conn.execute("DELETE FROM sqlite_sequence WHERE name='system_events'")
            deleted["system_events"] = events_before

        conn.commit()

    return deleted


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Purge l'historique du datalogger (mesures, optionnellement evenements)."
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        default=settings.db_path,
        help="Chemin vers la base SQLite (defaut: settings.db_path).",
    )
    parser.add_argument(
        "--include-events",
        action="store_true",
        help="Supprimer aussi l'historique des evenements systeme.",
    )
    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="Ne pas creer de sauvegarde avant purge.",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Confirmer automatiquement la purge.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    db_path = Path(args.db_path)

    if not db_path.exists():
        print(f"Base introuvable: {db_path}")
        print("Initialisation d'une base vide...")
        created = init_database()
        print(f"Base creee: {created}")
        return 0

    print(f"Base cible: {db_path}")
    print("Action: purge de la table measurements")
    if args.include_events:
        print("Action additionnelle: purge de la table system_events")

    if not args.yes:
        answer = input("Confirmer la purge ? (oui/non): ").strip().lower()
        if answer not in {"oui", "o", "yes", "y"}:
            print("Purge annulee.")
            return 1

    if not args.no_backup:
        backup_path = backup_database(db_path)
        print(f"Sauvegarde creee: {backup_path}")

    deleted = purge_history(db_path, include_events=args.include_events)

    print("Purge terminee.")
    print(f"Lignes supprimees measurements: {deleted.get('measurements', 0)}")
    if args.include_events:
        print(f"Lignes supprimees system_events: {deleted.get('system_events', 0)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
