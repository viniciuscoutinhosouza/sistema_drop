"""Run a SQL migration script against the Oracle database."""

import sys

import oracledb

from config import get_settings

settings = get_settings()
oracledb.defaults.fetch_lobs = False


def run(sql_file: str):
    kwargs = dict(  # noqa: C408 — modified conditionally below, cannot use literal
        user=settings.ORACLE_USER,
        password=settings.ORACLE_PASSWORD,
        dsn=settings.ORACLE_DSN,
    )
    if settings.ORACLE_WALLET_DIR:
        kwargs["config_dir"] = settings.ORACLE_WALLET_DIR
        kwargs["wallet_location"] = settings.ORACLE_WALLET_DIR
        kwargs["wallet_password"] = settings.ORACLE_WALLET_PASSWORD

    with open(sql_file, encoding="utf-8") as f:
        content = f.read()

    # Split on lines that are just "/" (PL/SQL block terminator)
    import re

    blocks = [b.strip() for b in re.split(r"\n\s*/\s*\n", content) if b.strip()]

    conn = oracledb.connect(**kwargs)
    cur = conn.cursor()
    errors = 0
    for block in blocks:
        block = block.strip()
        # Remove trailing "/" if present at end of block
        block = re.sub(r"\s*/\s*$", "", block).strip()
        # Only strip trailing ";" for plain DDL (no BEGIN/END)
        is_plsql = bool(re.search(r"\bBEGIN\b|\bDECLARE\b", block, re.IGNORECASE))
        if not is_plsql:
            block = block.rstrip(";").strip()
        # Strip leading comment lines
        lines = [l for l in block.splitlines() if not l.strip().startswith("--")]
        block = "\n".join(lines).strip()
        if not block:
            continue
        try:
            cur.execute(block)
            print(f"OK: {block[:60].replace(chr(10), ' ')}...")
        except oracledb.DatabaseError as e:
            print(f"ERR: {e} | {block[:60].replace(chr(10), ' ')}...")
            errors += 1
    conn.commit()
    cur.close()
    conn.close()
    print(f"\nConcluído — {len(blocks)} blocos, {errors} erro(s).")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python run_migration.py <caminho_do_sql>")
        sys.exit(1)
    run(sys.argv[1])
