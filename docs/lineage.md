# Data Lineage (AP 2.4)

> System-Ebene der Herkunftsdokumentation. Die **Feld-Ebene** (jede Silver-Spalte →
> Raw-Feld → Transformationsregel) steht vollständig in `cleaned_schema_AP1.1.md`
> (Abschnitt „Data-Lineage") und wird hier bewusst nicht dupliziert (U1).

## 1. Datenfluss (System-Ebene)

```
QUELLEN (extern, read-only)                    RAW / BRONZE (WORM, git-versioniert)
─────────────────────────────                  ───────────────────────────────────────
Open-Meteo /v1/forecast          ──┐
Open-Meteo /v1/archive           ──┼─ stündl. ─→  data/raw/weather/weather_<D>.ndjson
                                   │              (1 Zeile = 1 Abruf, _meta + response)
Polymarket Gamma /public-search  ──┤
Polymarket Gamma /events         ──┼─ stündl. ─→  data/raw/polymarket/polymarket_<D>.ndjson
Polymarket CLOB  /midpoint,/price──┘              (gamma_events + clob_quotes verbatim)
Polymarket Gamma /events?slug=   ──── täglich ─→  data/raw/polymarket/resolutions_<D>.ndjson
                                                  (aufgelöste Events, einmalig je Markt)
Open-Meteo previous-runs API     ── einmalig ──→  data/backfill/weather_<c>_prevday1.json
Polymarket CLOB /prices-history  ── einmalig ──→  data/backfill/polymarket_<c>_history.json

                    │  build_silver.py  (deterministischer Full-Rebuild, QS-Checks,
                    │   D2-As-of-Cut, D3-Label, Dedup, Einheiten; transform_version=Git-Hash)
                    ▼
CLEANED / SILVER    data/processed/silver.duckdb  ·  Tabelle market_bucket_daily
(derived, ignoriert)data/processed/silver/market_bucket_daily/city=*/  (Parquet)
                    │
                    ▼
ANALYSIS / GOLD     (AP 3.x — Feature-Tabelle, Modelle; noch nicht gebaut)
```

## 2. Quellen-Register

| Quelle | Endpoint | Kadenz | Lizenz/Zugang | Landet in |
|---|---|---|---|---|
| Open-Meteo Forecast | `api.open-meteo.com/v1/forecast` | stündlich | CC BY 4.0, keyless | weather_*.ndjson (`kind=weather-forecast`) |
| Open-Meteo Archiv (ERA5) | `archive-api.open-meteo.com/v1/archive` | stündlich | CC BY 4.0, keyless | weather_*.ndjson (`kind=weather-archive`) |
| Polymarket Gamma | `gamma-api.polymarket.com` | stündlich | öffentlich, read-only | polymarket_*.ndjson (`gamma_events`) |
| Polymarket CLOB | `clob.polymarket.com` | stündlich | öffentlich, read-only | polymarket_*.ndjson (`clob_quotes`) |
| Gamma Resolutions | `…/events?slug=` | täglich, idempotent | öffentlich | resolutions_*.ndjson |
| Open-Meteo Previous Runs | `previous-runs-api.open-meteo.com` | einmalig (AP 1.3) | CC BY 4.0 | backfill/weather_*_prevday1.json |
| CLOB Preis-Historie | `…/prices-history` | einmalig (Juni) | öffentlich | backfill/polymarket_*_history.json |

Koordinaten aller Wetter-Abrufe = **Auflösungsstation** des jeweiligen Markts
(EGLC, EDDM, KLGA, RJTT) — dokumentierte Ausnahme: 11 Alt-Records vom 16./20.06.
(München Stadtzentrum), per `station`-Kriterium vom Label ausgeschlossen.

## 3. Lineage je Zeile (Rückverfolgbarkeit in der Praxis)

Jede Silver-Zeile trägt ihre Herkunft als Daten:
`market_asof_ts` / `forecast_asof_ts` (exakte Quell-Snapshots) · `event_slug`/`market_id`/
`clob_token_yes` (API-Objekt-IDs) · `label_source` · `source` (live/backfill) ·
`transform_version` (Git-Commit des Transforms) · `created_at` (Lauf-Zeitpunkt).

**Demonstration:** `scripts/inspect/05_trace_lineage.py <Stadt> <Datum> <Bucket>` druckt
die komplette Kette. Beispiel (gekürzt, realer Lauf 13.07.):

```
SILVER  Munich | 2026-07-05 | 24°C  (source=live, transform=9e3ab69)
  yes_price_raw=0.37  forecast_max=24.5  observed_max=24.0  winner=26°C
1) MARKT-SNAPSHOT   polymarket_2026-07-04.ndjson, Zeile 117  (21:14:18Z, outcomePrices ["0.37","0.63"])
2) FORECAST         weather_2026-07-04.ndjson,   Zeile 217  (21:14:01Z, max[05.07.]=24.5)
3) LABEL (Archiv)   weather_2026-07-12.ndjson,   Zeile 314  (jüngster von 243 Abrufen, 24.0 °C)
4) RESOLUTION       resolutions_2026-07-11.ndjson, Zeile 16 (closed=true, winner 26°C)
```

Damit ist jeder Wert der Analyse bis zur originalen API-Antwort (Datei + Zeile) belegbar —
und weil Raw im Git-Repo versioniert ist, zusätzlich bis zum Commit-Zeitpunkt.

## 4. Bekannte Lineage-Vorfälle (Beleg für den Nutzen)

| Vorfall | Entdeckt durch | Konsequenz |
|---|---|---|
| München-Koordinatenwechsel 20.06. (1,5 °C Sprung) | `_meta.latitude/longitude` je Record | Label-Regel „nur Stations-Records" (D3) |
| ERA5-Revisionen (32/112 Tage) | mehrfache Archiv-Abrufe vergleichbar | „jüngster Abruf gewinnt" (D3) |
| Forecast-Lead-Inkonsistenz im Backfill | `_meta.kind`/Quelle unterscheidbar | Previous-Runs-API statt historical-forecast (AP 1.3/U1) |
