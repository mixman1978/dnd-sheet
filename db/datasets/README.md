# Datasets (spell & bestiario) — D&D Sheet

Questa cartella contiene i **dataset sorgente** (in JSON) usati per popolare il database locale dell’app.

## Obiettivo
- Tenere su GitHub **solo dati “catalogo”** (incantesimi/bestiario) che possono essere condivisi nel progetto.
- Tenere **privati** i personaggi (`characters`) dentro `db/dnd_sheet.sqlite3`, che è ignorato da git.

## Nota su licenze/copyright (importante)
I dataset in questa cartella devono contenere **solo**:
- contenuti **SRD/CC** (es. SRD 5.1 in CC-BY 4.0) con attribuzione presente in `docs/`, oppure
- dati originali creati da noi.

⚠️ **Non inserire** contenuti testuali o materiali provenienti da manuali non-SRD (PHB, Xanathar, Tasha, ecc.).
Vedi:
- `../../docs/ATTRIBUTION_SPELLS_SRD.md`
- `../../docs/ATTRIBUTION_SRD_CC.md`


## File attesi
- `spells_srd_it.json` → dataset finale per import spells
- `monsters_srd_it.json` → dataset finale per import bestiario
- (debug) `*_raw.json` → output grezzo (se presente, idealmente ignorato da git)

## Attribuzione / Licenze
- Spell SRD: `../../docs/ATTRIBUTION_SPELLS_SRD.md`
- Mostri SRD/CC: `../../docs/ATTRIBUTION_SRD_CC.md`

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
