# engine/db.py
from __future__ import annotations

import sqlite3
from pathlib import Path


# Root progetto (cartella che contiene main.py)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_ROOT = PROJECT_ROOT / "db"
SQLITE_PATH = DB_ROOT / "dnd_sheet.sqlite3"


def connect() -> sqlite3.Connection:
    """Connessione SQLite con PRAGMA utili e row_factory."""
    DB_ROOT.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(SQLITE_PATH)
    conn.row_factory = sqlite3.Row

    # PRAGMA: foreign keys, journaling sicuro, ecc.
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    return conn


def ensure_schema(conn: sqlite3.Connection) -> None:
    """Crea lo schema DB (idempotente)."""
    conn.executescript(
        """
        -- =========================================
        -- Meta / migrazioni (semplice)
        -- =========================================
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            applied_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        -- =========================================
        -- CHARACTERS (PG)
        -- =========================================
        CREATE TABLE IF NOT EXISTS characters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            -- Chiave "umana" usata oggi dalla UI (dropdown).
            name TEXT NOT NULL UNIQUE,

            -- Chiave stabile futura (può restare NULL finché non la usiamo).
            slug TEXT UNIQUE,

            -- Stato completo del PG (flessibile: non ti costringe a migrazioni frequenti)
            data_json TEXT NOT NULL,

            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_characters_name ON characters(name);
        CREATE INDEX IF NOT EXISTS idx_characters_slug ON characters(slug);


        -- =========================================
        -- SPELLS (catalogo)
        -- Descrizioni parafrasate (no testo dei libri)
        -- =========================================
        CREATE TABLE IF NOT EXISTS spells (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            slug TEXT NOT NULL UNIQUE,
            name_it TEXT NOT NULL,
            level INTEGER NOT NULL,              -- 0 = trucchetto
            school TEXT NOT NULL,                -- es: "Invocazione", "Abiurazione"...
            casting_time TEXT NOT NULL,          -- es: "1 azione", "1 reazione"...
            range_text TEXT NOT NULL,            -- es: "18 m", "Sé", "Contatto"...
            components_v INTEGER NOT NULL DEFAULT 0,
            components_s INTEGER NOT NULL DEFAULT 0,
            components_m INTEGER NOT NULL DEFAULT 0,
            material_text TEXT,                  -- testo libero (se M=1)
            duration_text TEXT NOT NULL,         -- es: "Istantanea", "1 minuto"...
            concentration INTEGER NOT NULL DEFAULT 0,
            ritual INTEGER NOT NULL DEFAULT 0,

            description TEXT NOT NULL,           -- parafrasi
            at_higher_levels TEXT,               -- parafrasi, opzionale
            source TEXT,                         -- es: "PHB", "Tasha"

            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_spells_name_it ON spells(name_it);
        CREATE INDEX IF NOT EXISTS idx_spells_level ON spells(level);
        CREATE INDEX IF NOT EXISTS idx_spells_school ON spells(school);


        -- Classi (per mapping spell <-> classi)
        CREATE TABLE IF NOT EXISTS classes (
            code TEXT PRIMARY KEY,   -- es: "wizard", "cleric", "druid"...
            name_it TEXT NOT NULL
        );

        -- Molti-a-molti: quali classi hanno accesso a quali incantesimi
        CREATE TABLE IF NOT EXISTS spell_classes (
            spell_id INTEGER NOT NULL,
            class_code TEXT NOT NULL,

            PRIMARY KEY (spell_id, class_code),
            FOREIGN KEY (spell_id) REFERENCES spells(id) ON DELETE CASCADE,
            FOREIGN KEY (class_code) REFERENCES classes(code) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_spell_classes_class ON spell_classes(class_code);


        -- =========================================
        -- MOSTERS (bestiario)
        -- =========================================
        CREATE TABLE IF NOT EXISTS monsters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            slug TEXT NOT NULL UNIQUE,
            name_it TEXT NOT NULL,
            cr REAL NOT NULL,                  -- GS (Challenge Rating)
            size TEXT NOT NULL,                -- es: "Piccola", "Media"...
            type TEXT NOT NULL,                -- es: "Umanoide", "Bestia"...
            alignment TEXT,                    -- testo libero

            ac INTEGER,                        -- opzionale
            hp INTEGER,                        -- opzionale
            speed_text TEXT,                   -- testo libero (es: "9 m, volare 18 m")

            senses_text TEXT,
            languages_text TEXT,

            -- Campi “semi-strutturati” in JSON (azioni/abilità ecc.)
            stats_json TEXT,                   -- For/Des/Con/Int/Sag/Car
            traits_json TEXT,
            actions_json TEXT,
            reactions_json TEXT,
            legendary_actions_json TEXT,

            description TEXT,                  -- parafrasi/riassunto (opzionale)
            source TEXT,

            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_monsters_name_it ON monsters(name_it);
        CREATE INDEX IF NOT EXISTS idx_monsters_cr ON monsters(cr);
        CREATE INDEX IF NOT EXISTS idx_monsters_type ON monsters(type);


        -- Tag (riutilizzabili)
        CREATE TABLE IF NOT EXISTS tags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE
        );

        CREATE TABLE IF NOT EXISTS monster_tags (
            monster_id INTEGER NOT NULL,
            tag_id INTEGER NOT NULL,

            PRIMARY KEY (monster_id, tag_id),
            FOREIGN KEY (monster_id) REFERENCES monsters(id) ON DELETE CASCADE,
            FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_monster_tags_tag ON monster_tags(tag_id);


        -- =========================================
        -- RELAZIONI PG <-> INCANTESIMI
        -- (serve dopo, ma meglio averla pronta)
        -- =========================================
        CREATE TABLE IF NOT EXISTS character_spells (
            character_id INTEGER NOT NULL,
            spell_id INTEGER NOT NULL,

            -- known / prepared / always / pact ecc. (stringa, semplice)
            status TEXT NOT NULL,

            -- opzionale: da quale classe/sottoclasse arriva (se multiclasse)
            source_class_code TEXT,

            notes TEXT,

            PRIMARY KEY (character_id, spell_id, status),
            FOREIGN KEY (character_id) REFERENCES characters(id) ON DELETE CASCADE,
            FOREIGN KEY (spell_id) REFERENCES spells(id) ON DELETE CASCADE,
            FOREIGN KEY (source_class_code) REFERENCES classes(code) ON DELETE SET NULL
        );

        CREATE INDEX IF NOT EXISTS idx_character_spells_character ON character_spells(character_id);
        CREATE INDEX IF NOT EXISTS idx_character_spells_spell ON character_spells(spell_id);
        """
    )
    conn.commit()
