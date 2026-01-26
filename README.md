# dnd-sheet
A local-first D&D 5e character sheet web app (NiceGUI), with spells, companions, and player-safe bestiary.

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

# importazione delle taballe
python scripts/import_spells_srd.py

# seed tabelle base
python scripts/seed_classes.py

# bestiario: genera dataset da SRD/CC e importa
python scripts/convert_monsters_cc_srd_to_dataset.py
python scripts/import_monsters_srd.py

