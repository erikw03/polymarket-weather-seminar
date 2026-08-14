# Anhang

*Zählt nicht zum Wortlimit. Vollständiger Quellcode und alle Entscheidungsprotokolle:
`github.com/erikw03/polymarket-weather-seminar`*

---

## A — Architektur der Pipeline

```
QUELLEN (öffentlich, read-only)              BRONZE (WORM, git-versioniert)
──────────────────────────────               ────────────────────────────────────
Open-Meteo  /v1/forecast      ──┐
Open-Meteo  /v1/archive       ──┼─ stündl. ─→ data/raw/weather/weather_<D>.ndjson
Polymarket  Gamma /events     ──┤
Polymarket  CLOB  /midpoint   ──┼─ stündl. ─→ data/raw/polymarket/polymarket_<D>.ndjson
Polymarket  Gamma /events?slug ─── täglich ─→ data/raw/polymarket/resolutions_<D>.ndjson

                     │  build_silver.py   (As-of-Schnitt, Label, Normalisierung,
                     │                     Dedup, 4 QS-Abbrüche, Full-Rebuild)
                     ▼
SILVER   data/processed/silver.duckdb  ·  market_bucket_daily  (+ Parquet, part. city)
                     │  build_features.py
                     ▼
GOLD     data/processed/analysis.duckdb · feature_table  →  model_framework.py
```

## B — Kennzahlen des Korpus (Data Freeze 14.08.2026)

| Größe | Wert |
|---|---|
| Abgedeckter Zeitraum | 01.03.–14.08.2026 (57 Sammeltage live + Backfill) |
| Bronze | 1.034 MB, 149 Tagesdateien, 39–45 Abrufe je Stadt und Tag |
| Silver | 6.887 Zeilen, 635 Stadt-Tage |
| Gold | 6.708 Zeilen, 618 Stadt-Tage |
| Full-Rebuild Bronze → Gold | 4,2 s (ein Rechenkern) |
| Qualitätsprüfungen | 18/18 bestanden |
| Resilienz-Nachweise | 8/8 bestanden |

## C — Auszug Silver-Schema (Grain: Stadt × Zieltag × Bucket)

| Spalte | Typ | Bedeutung |
|---|---|---|
| `city`, `target_date`, `bucket_label` | TEXT/DATE | zusammengesetzter Schlüssel |
| `yes_price_raw` / `yes_price_norm` | DOUBLE | implizite Wahrscheinlichkeit, roh / normiert |
| `overround_sum` | DOUBLE | Summe aller Bucket-Preise (Marktfriktion, ~1,02) |
| `forecast_max_c` | DOUBLE | Prognosemaximum zum As-of-Zeitpunkt |
| `observed_max_native` | DOUBLE | beobachtetes Tagesmaximum (Reanalyse) |
| `label_is_winner_official` | BOOLEAN | **Zielgröße:** amtliches Marktergebnis |
| `label_in_bucket` | BOOLEAN | Sekundärlabel aus Reanalyse (Vergleich) |
| `market_asof_ts` / `hours_to_event_end` | TIMESTAMP/DOUBLE | Herkunftszeit / Leakage-Audit |
| `source`, `transform_version`, `created_at` | TEXT/TS | Reproduzierbarkeit |

*Vollständige Spalten- und Lineage-Tabelle: `docs/cleaned_schema_AP1.1.md`*

## D — Kern der As-of-Logik (Leakage-Schutz), `build_silver.py`

```python
def cutoff(city: str, target_date: dt.date) -> dt.datetime:
    """D2 as-of cut: 00:00 local time of the target day, as UTC instant."""
    return dt.datetime.combine(target_date, dt.time(0, 0),
                               tzinfo=TZ[city]).astimezone(dt.timezone.utc)

# ... je (Stadt, Zieltag) gewinnt der letzte Snapshot VOR diesem Schnitt:
cut = cutoff(city, td)
if ts >= cut:
    continue          # Snapshot nach dem Schnitt: nie ein Merkmal (Leakage-Regel)
if key not in best or ts > best[key][0]:
    best[key] = (ts, ev, rec.get("clob_quotes", {}))
```

## E — Qualitätsprüfungen mit Abbruch, `build_silver.py`

```python
dupes      = ...  # Schlüsseleindeutigkeit (city, target_date, bucket_label)
bad_label  = ...  # genau ein Gewinner-Bucket je Zieltag
min_lead   = ...  # kleinster zeitlicher Vorlauf (Leakage-Audit)
norm_err   = ...  # Abweichung der normierten Verteilung von 1
if dupes or bad_label or bad_official:
    raise SystemExit("QS check failed - see log")
```

## F — Append-only Rohzone, `src/raw_store.py`

```python
def append_record(directory: pathlib.Path, source: str, record: dict) -> pathlib.Path:
    """Append one record as a line to today's NDJSON partition for `source`."""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{source}_{utc_date()}.ndjson"
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return path
```

## G — Betriebssteuerung (Auszug `.github/workflows/ingest.yml`)

```yaml
on:
  schedule:
    - cron: "17 * * * *"        # off-peak; zweiter Auslöser extern (Redundanz)
  workflow_dispatch: {}
concurrency:
  group: ingestion              # keine überlappenden Läufe
jobs:
  ingest:
    steps:
      - run: python run_ingestion.py          # 3 Quellen, gegeneinander isoliert
      - run: |                                # Daten sichern (vor dem Gate!)
          git add data/raw && git commit -m "data: ingestion snapshot ..."
      - run: python build_silver.py           # Silver frisch bauen
      - run: python quality_checks.py         # Gate: exit 1 bei FAIL → rote Mail
```

## H — Ergebnisse der Modellierung (420 Test-Tage, identische Zeit-Folds)

| Prädiktor | Brier ↓ | Log Loss ↓ | Trefferquote ↑ | ECE ↓ |
|---|---|---|---|---|
| Markt (Baseline) | **0,659** | **1,308** | **47,5 %** | **0,0110** |
| Logistische Regression | 0,787 | 1,749 | 33,3 % | 0,0117 |
| Gradient Boosting (kalibriert) | 0,784 | 1,751 | 32,2 % | – |
| Naive Prognoseregel | 1,292 | 4,125 | 31,7 % | – |

*Validierung: fortschreitende Zeitfenster, zwei Tage Sperrfrist wegen verzögerter
amtlicher Ergebnisse. Bewertet wird die je Stadt und Tag normierte Verteilung.*

## I — Dokumentierte Betriebsvorfälle

| Datum | Vorfall | Maßnahme |
|---|---|---|
| 21.06. | Zeitplan-Dienst lieferte keine Läufe | zweiter, unabhängiger Auslöser |
| 21.07. | Zwei gleichzeitige Läufe → Konflikt beim Zusammenführen | Merge-Strategie „union" + Wiederholung beim Schreiben |
| 30.07. | Fehlalarm: frisch gelisteter Markt ohne Preise | Prüfung nach Schweregrad getrennt |

## J — Verzeichnis der Projektartefakte

| Datei | Inhalt |
|---|---|
| `run_ingestion.py`, `src/ingest_*.py` | Erfassung der drei Quellen |
| `build_silver.py`, `build_features.py` | Transformation Bronze → Silver → Gold |
| `quality_checks.py`, `anomaly_checks.py` | 18 Qualitäts- + 8 Plausibilitätsprüfungen |
| `scripts/harden/test_resilience.py` | 8 Fehlertoleranz-Nachweise |
| `model_framework.py`, `scripts/analysis/` | Validierung, Modelle, Auswertung |
| `docs/cleaned_schema_AP1.1.md` | Schema + vollständige Lineage-Tabelle |
| `docs/DECISIONS_AP*.md` | Entscheidungsprotokolle aller Arbeitspakete |
| `docs/freeze/` | eingefrorene Kennzahlen und Ergebnis-Artefakte |
