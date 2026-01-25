import sys
from pathlib import Path

# Root del progetto (così trova "engine")
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.db import connect  # usa lo stesso DB/path del progetto


def q1(conn, sql: str, params=()):
    cur = conn.execute(sql, params)
    return cur.fetchone()


def qall(conn, sql: str, params=()):
    cur = conn.execute(sql, params)
    return cur.fetchall()


def table_exists(conn, name: str) -> bool:
    row = q1(
        conn,
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    )
    return row is not None


def column_exists(conn, table: str, col: str) -> bool:
    rows = qall(conn, f"PRAGMA table_info({table})")
    return any(r[1] == col for r in rows)  # r[1] = name colonna


def main():
    conn = connect()

    if not table_exists(conn, "spells"):
        print("ERRORE: tabella 'spells' non esiste nel DB.")
        return

    # 1) Conteggio totale
    total = q1(conn, "SELECT COUNT(*) FROM spells")[0]
    print(f"Totale spells nel DB: {total}")

    # 2) Controllo duplicati slug (dovrebbe essere 0)
    dup = q1(
        conn,
        """
        SELECT COUNT(*) FROM (
            SELECT slug, COUNT(*) c
            FROM spells
            GROUP BY slug
            HAVING c > 1
        )
        """,
    )[0]
    print(f"Slug duplicati: {dup}")

    # 3) Missing fields (adattivo: controlla solo colonne che esistono)
    checks = [
        ("name", "Nome vuoto"),
        ("slug", "Slug vuoto"),
        ("level", "Level NULL"),
        ("school", "School vuota/NULL"),
        ("casting_time", "Casting time vuoto/NULL"),
        ("range", "Range vuoto/NULL"),
        ("duration", "Duration vuota/NULL"),
        ("components", "Components vuoto/NULL"),
        ("description", "Description vuota/NULL"),
        ("higher_levels", "Higher levels vuoto/NULL"),
        ("ritual", "Ritual NULL"),
        ("concentration", "Concentration NULL"),
    ]

    print("\nMissing/Anomalie (solo colonne presenti):")
    for col, label in checks:
        if not column_exists(conn, "spells", col):
            continue

        if col in ("level", "ritual", "concentration"):
            n = q1(conn, f"SELECT COUNT(*) FROM spells WHERE {col} IS NULL")[0]
            if n:
                print(f"- {label}: {n}")
        else:
            n = q1(
                conn,
                f"SELECT COUNT(*) FROM spells WHERE {col} IS NULL OR TRIM({col}) = ''",
            )[0]
            if n:
                print(f"- {label}: {n}")

    # 4) Distribuzione livelli (se esiste 'level')
    if column_exists(conn, "spells", "level"):
        print("\nDistribuzione per livello:")
        rows = qall(
            conn,
            "SELECT level, COUNT(*) FROM spells GROUP BY level ORDER BY level",
        )
        for lvl, cnt in rows:
            print(f"- Livello {lvl}: {cnt}")

    # 5) Campione di 10 spell (ordinamento random)
    cols_to_show = []
    for c in ("name", "slug", "level", "school", "casting_time", "range", "duration", "components"):
        if column_exists(conn, "spells", c):
            cols_to_show.append(c)

    print("\nCampione (10 spell):")
    if cols_to_show:
        sql = f"SELECT {', '.join(cols_to_show)} FROM spells ORDER BY RANDOM() LIMIT 10"
        rows = qall(conn, sql)
        for r in rows:
            # stampa in formato leggibile
            out = " | ".join(str(x) if x is not None else "NULL" for x in r)
            print(f"- {out}")
    else:
        print("(Nessuna colonna riconosciuta da stampare)")

    # 6) Relazioni classi (se presenti)
    if table_exists(conn, "spell_classes"):
        sc = q1(conn, "SELECT COUNT(*) FROM spell_classes")[0]
        print(f"\nRighe in spell_classes: {sc}")
    else:
        print("\nTabella spell_classes: NON presente (ok se non l'hai ancora creata)")

    conn.close()


if __name__ == "__main__":
    main()
