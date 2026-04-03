"""
Run a SQL migration file against the Supabase PostgreSQL database.

Usage:
    python scripts/migrate.py                          # runs migrate-schema.sql
    python scripts/migrate.py --file migrate-phase5.sql  # runs a specific file

Requires:
    pip install psycopg2-binary python-dotenv
"""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load_env() -> dict[str, str]:
    env_path = ROOT / ".env"
    if not env_path.exists():
        print("[ERROR] .env file not found at project root.")
        sys.exit(1)

    env = {}
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        env[key.strip()] = value.strip()
    return env


def normalize_database_url(database_url: str) -> str:
    # psycopg2 expects a standard PostgreSQL DSN, not SQLAlchemy async dialects.
    return database_url.replace("postgresql+asyncpg://", "postgresql://", 1)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", default="migrate-schema.sql", help="SQL file to run (relative to project root)")
    args = parser.parse_args()
    try:
        import psycopg2
    except ImportError:
        print("[ERROR] psycopg2-binary is not installed.")
        print("        Run: pip install psycopg2-binary")
        sys.exit(1)

    env = load_env()
    database_url = env.get("DATABASE_URL")
    if not database_url:
        print("[ERROR] DATABASE_URL not found in .env")
        sys.exit(1)

    database_url = normalize_database_url(database_url)

    sql_path = ROOT / args.file
    if not sql_path.exists():
        print(f"[ERROR] {args.file} not found at: {sql_path}")
        sys.exit(1)

    sql = sql_path.read_text(encoding="utf-8")

    print(f"[INFO]  Connecting to database...")
    try:
        conn = psycopg2.connect(database_url)
        conn.autocommit = True
    except Exception as e:
        print(f"[ERROR] Could not connect to database: {e}")
        sys.exit(1)

    print(f"[INFO]  Running {args.file} ...")
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
        print("[OK]    Migration completed successfully.")
    except Exception as e:
        print(f"[ERROR] Migration failed: {e}")
        conn.close()
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
