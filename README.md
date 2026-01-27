# dnd-sheet
A local-first D&D 5e character sheet web app (Flask), with spells, companions, and player-safe bestiary.

## Requisiti
- Python 3.11+ (consigliato: la versione del progetto)
- SQLite (incluso in Python)

## Attribuzione / Licenze (SRD)
Questo progetto include materiale tratto dallo SRD 5.1 / CC-BY 4.0. Vedi:
- [docs/ATTRIBUTION_SPELLS_SRD.md](docs/ATTRIBUTION_SPELLS_SRD.md)
- [docs/ATTRIBUTION_SRD_CC.md](docs/ATTRIBUTION_SRD_CC.md)

## Setup
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

# Creazione del DB
è necessario che nella cartella db non ci sia il file dnd_sheet.sqlite3

```bash
# creazione DB e importazione spells
python scripts/import_spells_srd.py

# seed tabelle base
python scripts/seed_classes.py

# bestiario: import del bestiario
python scripts/import_monsters_srd.py

```

## Salvataggi PG
- Compila il personaggio e clicca **Salva** (usa il campo Nome come chiave univoca).
- Usa il menu **Personaggi salvati** + **Carica** per ripristinare dal DB.
- **Export JSON** scarica lo stato completo del PG corrente.
- **Import** accetta un file `.json` esportato e lo normalizza automaticamente.
- Salva/Carica/Import aggiornano `session["pg"]` senza cambiare i calcoli.
- **Pulisci PG** cancella solo la tabella `characters` (personaggi salvati).
- Non tocca cataloghi come spells o monsters.