# pip install psycopg2-binary
import time
from typing import Dict, List, Any

import psycopg2
from psycopg2 import sql
from psycopg2.extras import RealDictCursor

import json
from datetime import datetime, date
from pathlib import Path
from collections.abc import Mapping, Sequence

def to_jsonable(obj):
    """
    Recursively convert *obj* so that the result can be passed to
    json.dump()/json.dumps() without raising “Object of type … is not JSON
    serializable”.

    Rules
    -----
    1. JSON-native primitives (str, int, float, bool, None) are returned as-is.
    2. datetime / date ➜ ISO-8601 string.
    3. dict-like ➜ dict whose *keys are strings* and whose values were processed
       recursively.
    4. list / tuple / set ➜ list whose elements were processed recursively.
    5. bytes / bytearray ➜ UTF-8 string (with replacement on errors).
    6. Anything else ➜ str(obj).
    """
    # 1 ── primitives ───────────────────────────────────────────────────────
    if obj is None or isinstance(obj, (bool, int, float, str)):
        return obj

    # 2 ── dates & times ────────────────────────────────────────────────────
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()

    # 3 ── mappings (dict, defaultdict, OrderedDict, …) ─────────────────────
    if isinstance(obj, Mapping):
        return {str(k): to_jsonable(v) for k, v in obj.items()}

    # 4 ── sequences / sets (but *not* strings or bytes) ────────────────────
    if isinstance(obj, Sequence) and not isinstance(obj, (str, bytes, bytearray)):
        return [to_jsonable(x) for x in obj]
    if isinstance(obj, set):
        return [to_jsonable(x) for x in obj]

    # 5 ── binary blobs ─────────────────────────────────────────────────────
    if isinstance(obj, (bytes, bytearray)):
        return obj.decode("utf-8", errors="replace")

    # 6 ── pathlib.Path ─────────────────────────────────────────────────────
    if isinstance(obj, Path):
        return str(obj)

    # 7 ── fallback ─────────────────────────────────────────────────────────
    return str(obj)


# --------------------------------------------------------------------------- #
# 1. Helper: connect with retry                                               #
# --------------------------------------------------------------------------- #
def _connect_with_retry(
    db_config: Dict[str, str],
    timeout: int = 60,
    delay: float = 1.0,
) -> psycopg2.extensions.connection:
    """
    Keep trying to open a psycopg2 connection for *timeout* seconds.
    """
    deadline = time.time() + timeout

    while True:
        try:
            return psycopg2.connect(
                host=db_config["db_host"],
                port=db_config["db_port"],
                user=db_config["db_username"],
                password=db_config["db_password"],
                dbname=db_config["db_name"],
            )
        except psycopg2.OperationalError as exc:
            # Give up when the overall timeout has elapsed
            if time.time() >= deadline:
                raise RuntimeError(
                    f"Could not connect to PostgreSQL after {timeout}s"
                ) from exc

            # Optional: comment-out the next line to silence the log
            print(f"[db-retry] {exc}. Retrying in {delay:.1f}s…")

            time.sleep(delay)


# --------------------------------------------------------------------------- #
# 2. Main routine: dump_database                                              #
# --------------------------------------------------------------------------- #
def dump_database(
    db_config: Dict[str, str],
    limit: int = 5,
    connect_timeout: int = 60,
) -> Dict[str, Dict[str, Any]]:
    """
    Scan every table and return at most *limit* rows per table.

    Output format:
    {
        "schema.table": {
            "columns": List[str],      #  <-- NEW
            "total_rows": int,
            "truncated": bool,
            "rows": List[dict]
        },
        ...
    }
    """
    result: Dict[str, Dict[str, Any]] = {}

    conn = _connect_with_retry(db_config, timeout=connect_timeout)
    try:
        with conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Discover ordinary user tables
            cur.execute(
                """
                SELECT table_schema, table_name
                FROM information_schema.tables
                WHERE table_type = 'BASE TABLE'
                  AND table_schema NOT IN ('pg_catalog', 'information_schema')
                ORDER BY table_schema, table_name
                """
            )

            for t in cur.fetchall():
                schema, table = t["table_schema"], t["table_name"]
                identifier = f"{schema}.{table}"

                # ------------------------------------------------------------------
                # 1. Column names (metadata)
                # ------------------------------------------------------------------
                cur.execute(
                    """
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_schema = %s AND table_name = %s
                    ORDER BY ordinal_position
                    """,
                    (schema, table),
                )
                columns = [row["column_name"] for row in cur.fetchall()]

                # ------------------------------------------------------------------
                # 2. Row count
                # ------------------------------------------------------------------
                cur.execute(
                    sql.SQL("SELECT COUNT(*) FROM {}.{}").format(
                        sql.Identifier(schema), sql.Identifier(table)
                    )
                )
                total_rows = cur.fetchone()["count"]

                # ------------------------------------------------------------------
                # 3. Sample rows
                # ------------------------------------------------------------------
                cur.execute(
                    sql.SQL("SELECT * FROM {}.{} LIMIT {}").format(
                        sql.Identifier(schema),
                        sql.Identifier(table),
                        sql.Literal(limit),
                    )
                )
                rows: List[dict] = cur.fetchall()  # RealDictCursor → dict per row

                result[identifier] = {
                    "columns": columns,          #  <-- NEW
                    "total_rows": total_rows,
                    "truncated": total_rows > limit,
                    "rows": rows,
                }
    finally:
        conn.close()

    return to_jsonable(result)


# --------------------------------------------------------------------------- #
# 3. Example usage                                                            #
# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    import json

    db_config = {
        "db_host": "localhost",
        "db_port": "5432",
        "db_username": "myappuser",
        "db_password": "myapppassword",
        "db_name": "myapp",
    }

    dump = dump_database(db_config, limit=5, connect_timeout=60)
    # default=str converts non-JSON-serialisable types (Decimal, UUID, datetime…)
    print(json.dumps(dump, indent=2, default=str))