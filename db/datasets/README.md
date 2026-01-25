# Datasets (spell & bestiario) — D&D Sheet

Questa cartella contiene i **dataset sorgente** (in JSON) usati per popolare il database locale dell’app.

## Obiettivo
- Tenere su GitHub **solo dati “catalogo”** (incantesimi/bestiario) che possono essere condivisi nel progetto.
- Tenere **privati** i personaggi (`characters`) dentro `db/dnd_sheet.sqlite3`, che è ignorato da git.

## Nota su copyright (importante)
I dataset **non devono** contenere testo copiato dai manuali (PHB, Xanathar, Tasha, ecc.).
- Usa **descrizioni originali/parafrasate** (stesso significato, testo diverso).
- Evita frasi riconoscibili o blocchi identici ai libri.
- I nomi degli incantesimi sono in **italiano**.

## File attesi
- `spells_srd_it.json` → spell SRD (IT) estratte e normalizzate (dataset “finale” usato per l’import)
- `spells_srd_it_raw.json` → output grezzo di debug (ignorato da git)
- `ATTRIBUTION_SRD.md` → attribuzione SRD / note licenza e fonti
- (futuro) `monsters_*.json` → bestiario strutturato/riassunto

> Suggerimento: tieni questi file “puliti” e coerenti. Il DB locale si può rigenerare in qualunque momento re-importando.

---

# Convenzioni generali

## Slug
Ogni record deve avere uno `slug` univoco:
- minuscolo
- parole separate da `-`
- solo lettere/numeri/trattini

Esempi:
- `dardo-incantato`
- `palla-di-fuoco`
- `goblin`
- `drago-rosso-giovane`

## Tipi e formati
- booleani: `true/false`
- liste: `[]`
- testo: stringhe UTF-8 (accenti ok)
- niente HTML dentro i campi testo (se possibile)

---

# Schema: `spells_it.json`

Il file è un array JSON:

```json
[
  { "slug": "...", "name_it": "...", "level": 0, "...": "..." }
]
