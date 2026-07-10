# Cleaned-Schema (Silver) — AP 1.1

> **STATUS: 🔶 VORSCHLAG (Phase B) — noch nicht freigegeben.**
> Entscheidungsvorlage D1–D6; Finalisierung erst nach Freigabe an STOPP 2.
> Grundlage: `docs/raw_inspection_report_AP1.1.md` (Phase A, Korpus-Stand 2026-07-10).

## Zweck

Übergang Raw(Bronze) → Cleaned(Silver) im Medallion-Ansatz: aus ~70 000 verrauschten,
stark duplizierten Bucket-Snapshots wird **eine deduplizierte, getypte, leakage-freie
Tabelle**, auf der AP 3 (Features/Modelle) direkt aufsetzen kann. Der Use-Case
(Modell-Wahrscheinlichkeit vs. markt-implizite Wahrscheinlichkeit je Temperatur-Bucket,
Metriken Brier/Log Loss/Accuracy) bestimmt das Design.

---

## D1 — Grain: 1 Zeile = Stadt × Zieltag × Bucket  🔶

**Empfehlung:** Grain = `(city, target_date, bucket_label)` — Sub-Market-Ebene.

**Begründung:**
- Die Zielmetriken (Brier, Log Loss) vergleichen je **Bucket** eine Modell- mit einer
  Markt-Wahrscheinlichkeit; das Grain muss also die Bucket-Ebene tragen.
- Auf Polymarket ist jeder Bucket technisch ein eigener binärer Markt (eigene `id`,
  `conditionId`, eigenes Orderbuch). Die Projektplan-Formulierung „1 Zeile = 1 Markt × 1 Tag"
  ist damit wörtlich erfüllt (1 Zeile = 1 Sub-Markt × 1 Tag); pro Event-Tag entstehen ~11 Zeilen.
- Aggregation nach oben (Event-Ebene, z. B. erwartete Temperatur aus der Verteilung) ist
  jederzeit per GROUP BY möglich — umgekehrt nicht.

**Alternative (verworfen):** 1 Zeile = Event × Tag mit 11 Preis-Spalten oder JSON-Array.
Verworfen, weil (a) Bucket-Anzahl/-Labels variieren (9–11 Buckets, °C vs. 2-°F-Bänder) →
Spaltenschema instabil; (b) Metriken pro Bucket dann doch wieder entpivotiert werden müssten.

**Erwartete Größe:** live ~86 Zieltage × ~11 Buckets ≈ 950 Zeilen; mit Backfill (AP 1.3,
423 Zieltage) ≈ 5 600 Zeilen. Bewusst klein — Silver ist das *destillat*, Raw bleibt vollständig.

---

## D2 — As-of-Politik: letzter Snapshot vor 00:00 Lokalzeit des Zieltags  🔶 (wichtigste Entscheidung)

**Empfehlung:** Für Markt **und** Forecast gilt derselbe Cut:
**as-of = letzter Abruf mit `fetched_at_utc` < 00:00 *Lokalzeit* des Zieltags** („Day-ahead-Politik").
Beide Quellen werden mit je *ihrem* letzten Snapshot vor diesem Cut eingefroren
(`market_asof_ts`, `forecast_asof_ts` dokumentieren das exakt).

**Begründung (Leakage):**
- Phase A hat belegt: der Preis wird im Tagesverlauf zum Label (London 22.06.: 09:01Z 0,40 →
  13:01Z 0,90 → 16:01Z 1,00), und Events bleiben bis D+1 im Feed. Jeder Cut *im* Zieltag
  riskiert, bereits realisierte Temperatur „einzupreisen" — auch vormittags (Teilinformation:
  „bis 10 Uhr schon 25 °C erreicht").
- Cut **vor Beginn des lokalen Zieltags** garantiert: das Tagesmaximum liegt vollständig in
  der Zukunft. Modell und Markt sehen denselben Informationsstand → fairer Vergleich.
- `endDate` (12:00Z) ist als Cut ungeeignet: nominell, nicht der Handelsschluss, und lokal
  bereits Nachmittag (Tokio 21:00, London 13:00).

**Alternativen:**
- *Fester Lead vor `endDate`* (z. B. 24 h vor 12:00Z): technisch einfach, aber der Cut fiele
  je Stadt auf andere Lokalzeit (NYC 08:00 morgens vs. Tokio 21:00 abends) → ungleiche
  Informationslage zwischen Städten. Verworfen.
- *Mehrere As-of-Leads als eigene Zeilen* (`asof_policy`-Dimension, z. B. D-1, D-2): wertvoll
  für Sensitivitätsanalysen, aber Scope-Inflation für AP 1. Vorgesehen: Spalte `asof_policy`
  (konstant `"D-1_2359_local"`) macht das Schema erweiterbar, ohne es jetzt zu bauen.

**Konsequenz:** Snapshots *nach* dem Cut werden für Features nie verwendet; `hours_to_event_end`
(Abstand as-of → `endDate`) wird gespeichert, damit Leakage jederzeit auditierbar ist.

---

## D3 — Label: Open-Meteo-Archive (jüngster Abruf), gerundet auf ganze Grad nativ  🔶

**Empfehlung:**
- `observed_max_native` = Tagesmax aus `weather-archive`, **jüngster Abruf gewinnt**
  (Phase A: ERA5-Revisionen und der München-Koordinatenwechsel machen „irgendein Abruf" mehrdeutig;
  zusätzlich nur Abrufe mit Flughafen-Koordinaten verwenden — schließt die 11 Alt-Records aus).
- **Bucket-Zuordnung in nativer Einheit auf ganze Grad gerundet** (kaufmännisch, half-up):
  27,4 °C → „27°C"; 84,6 °F → „84-85°F". Begründung: Wunderground/der Markt löst auf ganze
  Grad auf; Rundung in nativer Einheit vermeidet °F↔°C-Rundungsartefakte.
- `label_in_bucket` (bool) = liegt der gerundete Ist-Wert im Bucket-Intervall.
- Zusätzlich `market_resolved_bucket` (nullable): das markt-implizite Ergebnis, wo verfügbar
  (Backfill: 423 Zieltage; live: die 7 Events mit resolved-Spuren) + `labels_agree` (bool, nullable).

**Begründung der Quelle:** Open-Meteo deckt **100 %** der vergangenen Zieltage ab (Phase A),
liegt ab D+1 vor und funktioniert identisch für Live- und Backfill-Zeitraum. Markt-Resolution
ist im Live-Feed strukturell unzuverlässig (Roll-off, nur 0,1 % resolved-Snapshots).

**Dokumentierter Vorbehalt (Quellen-Mismatch):** Open-Meteo (Modell/Reanalyse am Gridpunkt) ≠
Wunderground-Stationsmessung; Backfill-Vergleich zeigte je Stadt mittlere Differenzen ~0,5–1 °C.
**Konsequenz für „Modell vs. Markt":** beide werden am *selben* Open-Meteo-Label gemessen →
der Vergleich ist intern konsistent; aber der Markt „zielt" auf Wunderground und trägt dadurch
einen kleinen systematischen Nachteil. Wird über `labels_agree` auf dem Backfill-Subset
quantifiziert und in der Arbeit als Limitation ausgewiesen.

**Alternative (verworfen als Primärquelle):** markt-implizites Ergebnis als Label — koppelt
Label an die zu evaluierende Quelle (zirkulär für den Markt-Baseline-Vergleich) und hat im
Live-Korpus Deckungslücken.

---

## D4 — Roll-off / Resolution-Absicherung  🔶

**Empfehlung (für dieses AP):** Label über Wetter-Archive (D3); zusätzlich je Bucket der letzte
Pre-Cut-Preis als **„market final estimate"** (das ist per D2 ohnehin der Feature-Preis).
Kein Versuch, aus den zufälligen 0,1 %-resolved-Snapshots des Live-Feeds Labels zu bauen.

**📌 To-do für AP 1.2 (Ingestion-Erweiterung, klein):** täglicher **Resolution-Fetcher** —
für Events vom Vortag per `GET /events?slug=<event_slug>` die aufgelöste Version abrufen
(liefert `outcomePrices` als `["1","0"]` je Bucket) und als eigene Raw-Quelle
`data/raw/polymarket/resolutions_YYYY-MM-DD.ndjson` appenden (WORM bleibt gewahrt).
Damit bekommt der Korpus ab AP 1.2 ein *offizielles* Markt-Label für jeden neuen Tag,
und `market_resolved_bucket`/`labels_agree` füllen sich vorwärts automatisch.

---

## D5 — Spaltenliste Silver-Tabelle `market_bucket_daily`  🔶

Typen = DuckDB. „nativ" = Einheit der Stadt (°C bzw. °F für NYC).

### Schlüssel
| Spalte | Typ | Null | Semantik |
|---|---|---|---|
| `city` | TEXT | nein | Stadtname wie im Markt („NYC", nicht „New York") — PK-Teil |
| `target_date` | DATE | nein | Zieltag (lokaler Kalendertag des Marktes) — PK-Teil |
| `bucket_label` | TEXT | nein | natives Bucket-Label („27°C", „32-33°F", „46°F or higher") — PK-Teil |

### Bucket-Geometrie (aus `bucket_label` geparst)
| Spalte | Typ | Null | Semantik |
|---|---|---|---|
| `bucket_kind` | TEXT | nein | `exact` \| `range` \| `below` \| `above` |
| `bucket_unit` | TEXT | nein | `C` \| `F` |
| `bucket_low_native` / `bucket_high_native` | DOUBLE | ja | Intervallgrenzen nativ; offener Rand → NULL |
| `bucket_mid_c` | DOUBLE | nein | Bucket-Mitte in °C (normalisiert, für Modell/Plots) |

### Markt-Features (Stand: `market_asof_ts`, D2-Cut)
| Spalte | Typ | Null | Semantik |
|---|---|---|---|
| `yes_price_raw` | DOUBLE | nein | `outcomePrices[0]` des Buckets (implizite Wahrscheinlichkeit, unkorrigiert) |
| `yes_price_norm` | DOUBLE | nein | `yes_price_raw / overround_sum` — Overround-korrigiert, Summe je Event = 1 |
| `overround_sum` | DOUBLE | nein | Summe aller Yes-Preise des Events beim as-of-Snapshot (QS + Lineage der Normierung) |
| `clob_mid` | DOUBLE | ja | Orderbuch-Midpoint aus `clob_quotes` (zweite Preisquelle; NULL wenn fehlend) |
| `bucket_volume` / `bucket_liquidity` | DOUBLE | ja | Volumen/Liquidität des Sub-Markts (`volumeNum`/`liquidityNum`) |
| `event_volume` / `event_liquidity` | DOUBLE | ja | dito auf Event-Ebene (Aktivitätsmaß des Gesamtmarkts) |
| `n_snapshots_pre_asof` | INTEGER | nein | Anzahl im Korpus vorhandener Snapshots bis zum Cut (Dichte-/QS-Maß) |
| `hours_to_event_end` | DOUBLE | nein | `endDate` − `market_asof_ts` in Stunden (Leakage-Audit, muss ≥ ~12 h sein) |

### Wetter-Features (Stand: `forecast_asof_ts`, gleicher D2-Cut)
| Spalte | Typ | Null | Semantik |
|---|---|---|---|
| `forecast_max_native` / `forecast_min_native` | DOUBLE | ja | prognostiziertes Tagesmax/-min für den Zieltag, nativ |
| `forecast_max_c` / `forecast_min_c` | DOUBLE | ja | dito in °C (Modell-Einheit) |

### Label
| Spalte | Typ | Null | Semantik |
|---|---|---|---|
| `observed_max_native` | DOUBLE | ja | Ist-Tagesmax (Archive, jüngster Abruf, nur Stations-Koordinaten); NULL solange Zukunft |
| `observed_max_c` | DOUBLE | ja | dito °C |
| `observed_max_int_native` | INTEGER | ja | auf ganze Grad gerundet (half-up, nativ) — Basis der Bucket-Zuordnung |
| `label_in_bucket` | BOOLEAN | ja | **das Label:** gerundeter Ist-Wert liegt in diesem Bucket |
| `label_source` | TEXT | nein | konstant `open_meteo_archive_latest` (Lineage/Erweiterbarkeit) |
| `observed_lag_days` | INTEGER | ja | Tage bis erster Ist-Wert verfügbar war (Freshness-Doku) |
| `market_resolved_bucket` | TEXT | ja | markt-offizielles Gewinner-Bucket, wo bekannt (Backfill/Resolution-Fetcher) |
| `labels_agree` | BOOLEAN | ja | `market_resolved_bucket` ≙ Open-Meteo-Bucket (Mismatch-Quantifizierung) |

### Metadaten / Lineage / QS
| Spalte | Typ | Null | Semantik |
|---|---|---|---|
| `source` | TEXT | nein | `live` \| `backfill` |
| `asof_policy` | TEXT | nein | konstant `D-1_2359_local` (macht D2 explizit & erweiterbar) |
| `market_asof_ts` / `forecast_asof_ts` | TIMESTAMP | nein/ja | exakte Herkunfts-Snapshots (UTC) |
| `event_id` / `event_slug` / `market_id` | TEXT | nein | Gamma-IDs (Rück-Join in Raw) |
| `clob_token_yes` | TEXT | ja | Yes-Token-ID (Rück-Join in `clob_quotes`) |
| `station` / `resolution_source_url` | TEXT | nein | Auflösungsstation (Wetter-`_meta` / Event) |
| `temperature_unit` | TEXT | nein | `celsius` \| `fahrenheit` (nativ) |
| `flag_overround_outlier` | BOOLEAN | nein | \|`overround_sum`−1\| > 0,10 (frische Listings etc.) |
| `flag_partial_day` | BOOLEAN | nein | as-of-Tag ist Teiltag/Lückenrand (16./20.06., 10.07.) |
| `transform_version` / `created_at` | TEXT/TIMESTAMP | nein | Reproduzierbarkeit des Transform-Laufs |

*(Vollständige Lineage-Tabelle Silver-Spalte → Raw-Feld → Regel folgt in Phase C.)*

---

## D6 — Join-Logik & Einheiten-Strategie  🔶

**Joins:**
1. **Markt ⋈ Forecast:** über `(city, target_date)`; je Seite unabhängig der letzte Snapshot
   vor dem D2-Cut (Markt: Zeile mit `eventDate = target_date`; Wetter: `kind=weather-forecast`,
   Element des `daily`-Arrays mit `time = target_date`).
2. **Label-Join (datei-übergreifend):** `kind=weather-archive`-Records aller *späteren* Dateien;
   Element mit `time = target_date`; bei mehreren Abrufen gewinnt der jüngste `fetched_at_utc`
   (nur Stations-Koordinaten).
3. **Bucket-Zuordnung:** `observed_max_int_native` gegen `[bucket_low_native, bucket_high_native]`
   (Ränder inklusiv; `below`/`above` einseitig offen). Ganzzahlig + nativ ⇒ exakt und
   rundungsartefaktfrei; genau ein Bucket pro Zieltag matcht.

**Einheiten:** **nativ führen + °C-Normalisierung als Zusatzspalten** (`*_native` + `*_c`,
`temperature_unit`). Label-Logik läuft nativ (ganze Grad, wie der Markt auflöst); Modell nutzt
°C-Spalten für Cross-City-Vergleichbarkeit. Keine °F-Normalisierung (nur 1 von 4 Städten).

---

## Zusatz-Entscheidungen  🔶

- **Storage:** DuckDB-Datei `data/processed/silver.duckdb` (Tabelle `market_bucket_daily`)
  **+ Parquet-Export** `data/processed/silver/market_bucket_daily/city=<city>/*.parquet`
  (Partition nach `city`; bei ~5 600 Zeilen bewusst flach — Partitionierung nach Datum wäre
  Over-Engineering, wird aber im Text als Skalierungspfad erwähnt). DuckDB = Query-Komfort,
  Parquet = portables, spaltenorientiertes Austauschformat (Kapitel-Mapping K3/K4).
- **Idempotenz/Backfill-Tauglichkeit:** Transform (AP 1.2) als **deterministischer Full-Rebuild**
  aus Raw (drop & recreate). Bei dieser Korpusgröße (<10⁴ Zeilen aus ~360 MB Raw) ist das die
  einfachste korrekte Idempotenz-Strategie; Backfill (AP 1.3) = einfach erneut laufen lassen,
  `source`-Spalte unterscheidet Herkunft. Inkrementelles Laden wäre Betriebs-Optimierung, kein Muss.
- **Overround:** beide Preise führen (`yes_price_raw`, `yes_price_norm`) + `overround_sum` +
  Ausreißer-Flag. Modell/Metriken nutzen standardmäßig `yes_price_norm`; die Arbeit kann den
  Overround (~2–3 %) als Marktfriktion diskutieren.

---

## Offene Punkte für STOPP 2

1. D2: Ist „D-1 23:59 lokal" als *einziger* v1-Cut ok (statt zusätzlich z. B. „D-1 12:00Z")?
2. D3: Rundung half-up akzeptiert? (Alternative: floor — Wunderground-Konvention unklar.)
3. D5: Spaltenumfang ok oder kürzen (z. B. `clob_mid`, `event_*` weglassen)?
4. Zusatz: Parquet-Partitionierung nach `city` ok?
