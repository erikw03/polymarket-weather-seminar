# Cleaned-Schema (Silver) — AP 1.1

> **STATUS: ✅ FREIGEGEBEN (STOPP 2, 2026-07-10) — D1–D6 wie empfohlen.**
> Offene Punkte entschieden: D2-Cut = einzig „D-1 23:59 lokal" (v1) · Rundung half-up ·
> voller Spaltenumfang inkl. `clob_mid`/`event_*` · Parquet-Partition nach `city`.
> Grundlage: `docs/raw_inspection_report_AP1.1.md` (Phase A, Korpus-Stand 2026-07-10).
> Umsetzung des Transforms: **AP 1.2** (nicht Teil dieses AP).
>
> **🔄 D3-REVISION (AP 1.2, freigegeben 2026-07-12):** Die in D3 vorgesehene Quantifizierung
> ergab nur 23 % exakte Bucket-Übereinstimmung zwischen Open-Meteo-Label und offiziellem
> Markt-Ergebnis (München-Bias +2 °C; Details `DECISIONS_AP1.2.md`). Da der Resolution-Fetcher
> (AP 1.2) das offizielle Ergebnis inzwischen flächendeckend liefert, gilt:
> **Primäres Label = `label_is_winner_official`** (Bucket = offizielles Gewinner-Bucket aus
> `resolutions_*.ndjson`); das Open-Meteo-Label (`label_in_bucket`) bleibt als dokumentierte
> Sekundär-/Vergleichsspalte (Mismatch = quantifizierte Limitation).

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
| `label_is_winner_official` | BOOLEAN | ja | **das primäre Label (D3-Revision):** Bucket = offizielles Gewinner-Bucket der Markt-Resolution; NULL solange unaufgelöst |
| `label_in_bucket` | BOOLEAN | ja | Sekundär-Label: gerundeter Open-Meteo-Ist-Wert liegt in diesem Bucket |
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

## Data-Lineage: Silver-Spalte → Raw-Herkunft → Transformationsregel

Raw-Quellen: **[W]** `data/raw/weather/weather_<D>.ndjson` · **[P]** `data/raw/polymarket/polymarket_<D>.ndjson` · **[B]** `data/backfill/*.json` (ab AP 1.3).
Notation: `ev` = Element aus `gamma_events[]`, `mk` = Element aus `ev.markets[]`.

| Silver-Spalte | Raw-Herkunft | Transformationsregel |
|---|---|---|
| `city` | [P] `_meta.city` / [W] `_meta.city` | 1:1 (Kanon: Markt-Schreibweise, z. B. „NYC") |
| `target_date` | [P] `ev.eventDate` | 1:1 (Fallback `ev.endDate[:10]`; NICHT aus Abrufzeit ableiten) |
| `bucket_label` | [P] `mk.groupItemTitle` | 1:1 |
| `bucket_kind/…_low/…_high_native` | [P] `mk.groupItemTitle` | Regex-Parser, 4 Muster: `N°X` · `N-M°X` · `N°X or below` · `N°X or higher`; offener Rand → NULL |
| `bucket_unit` | [P] `mk.groupItemTitle` | „°F" im Label → `F`, sonst `C` |
| `bucket_mid_c` | abgeleitet | Mitte aus low/high (Rand: der endliche Wert); °F→°C: (x−32)·5/9 |
| `yes_price_raw` | [P] `mk.outcomePrices` | **doppelt** JSON-dekodieren → Element [0] → FLOAT; Snapshot = D2-Cut |
| `overround_sum` | [P] alle `mk.outcomePrices` des Events | Summe der Yes-Preise desselben Event-Snapshots |
| `yes_price_norm` | abgeleitet | `yes_price_raw / overround_sum` |
| `clob_mid` | [P] `clob_quotes[token].midpoint.mid` | Token = `json.loads(mk.clobTokenIds)[0]`; STRING→FLOAT; fehlend → NULL |
| `bucket_volume` / `bucket_liquidity` | [P] `mk.volumeNum` / `mk.liquidityNum` | numerische Varianten bevorzugen (String-Felder meiden) |
| `event_volume` / `event_liquidity` | [P] `ev.volume` / `ev.liquidity` | FLOAT-Cast; fehlend (0,5 %) → NULL |
| `n_snapshots_pre_asof` | [P] Zeilen je (city, eventDate) | COUNT über alle Snapshots mit `fetched_at_utc` < Cut |
| `hours_to_event_end` | [P] `ev.endDate` − `market_asof_ts` | Differenz in Stunden (Erwartung ≥ ~12 h, sonst QS-Alarm) |
| `market_asof_ts` | [P] `_meta.fetched_at_utc` | max(fetched_at) mit fetched_at < 00:00 Lokalzeit(target_date, city-TZ) |
| `forecast_asof_ts` | [W] `_meta.fetched_at_utc` | analog, `kind=weather-forecast` |
| `forecast_max/min_native` | [W] `response.daily.*[i]` | Index i mit `daily.time[i] == target_date`; Snapshot = D2-Cut |
| `forecast_max/min_c` | abgeleitet | °F→°C nur für NYC (`temperature_unit`) |
| `observed_max_native` | [W] `kind=weather-archive`, `response.daily.temperature_2m_max[i]` | `time[i]==target_date`; über ALLE späteren Dateien; **jüngster `fetched_at_utc` gewinnt**; nur Stations-Koordinaten (11 Alt-Records ausgeschlossen) |
| `observed_max_int_native` | abgeleitet | kaufmännische Rundung (half-up) auf ganze Grad, nativ |
| `label_in_bucket` | abgeleitet | `bucket_low ≤ observed_max_int ≤ bucket_high` (offene Ränder einseitig); genau 1 Bucket je Zieltag = true |
| `observed_lag_days` | [W] Dateiname vs. `target_date` | erster Dateitag mit Ist-Wert − Zieltag |
| `market_resolved_bucket` | [P] `resolutions_*.ndjson` → `event.markets[]` mit `outcomePrices[0] ≥ 0,99` → `groupItemTitle` (Fallback [B] `resolved_bucket`) | Gewinner-Bucket des aufgelösten Events |
| `label_is_winner_official` | abgeleitet | `bucket_label == market_resolved_bucket`; NULL wenn Resolution fehlt |
| `labels_agree` | abgeleitet | Vergleich der beiden Label-Quellen; NULL wenn eine fehlt |
| `event_id`/`event_slug`/`market_id` | [P] `ev.id`/`ev.slug`/`mk.id` | 1:1 |
| `clob_token_yes` | [P] `mk.clobTokenIds` | doppelt dekodieren → [0] |
| `station` | [W] `_meta.station` | 1:1 (Fallback aus City-Konfig für Alt-Records) |
| `resolution_source_url` | [P] `ev.resolutionSource` | 1:1 |
| `temperature_unit` | [W] `_meta.temperature_unit` | 1:1 (Fallback City-Konfig) |
| `source` | Dateipfad | `data/raw/…` → `live`; `data/backfill/…` → `backfill` |
| `asof_policy` | konstant | `D-1_2359_local` |
| `flag_overround_outlier` | abgeleitet | \|`overround_sum` − 1\| > 0,10 |
| `flag_partial_day` | Dateiebene | as-of-Datum ∈ {2026-06-16, 2026-06-20} ∪ Lückenränder ∪ letzter (unvollständiger) Sammeltag |
| `transform_version`/`created_at` | Transform-Lauf | Git-Hash bzw. Lauf-Zeitstempel |

Bewusst **nicht** übernommen (Begründung): Bild-/UI-Felder (`image`, `icon`, `series`, `tags`), Gebühren-/Reward-Felder, `eventMetadata.context_description` (Polymarket-eigener Prognosetext — für ein Sprachfeature interessant, aber out-of-scope), `bestBid/bestAsk/spread` (durch `clob_mid` abgedeckt), `oneDay/oneHourPriceChange` (aus eigener Zeitreihe rekonstruierbar). Raw behält alles.

---

## Bereit für AP 1.2 — Übergabe

Der Transform (AP 1.2) muss umsetzen, in dieser Reihenfolge:

1. **Dedup/As-of-Auswahl (D2):** je `(city, target_date)` und Quelle den letzten Snapshot vor
   00:00 Lokalzeit des Zieltags wählen (City-TZ: Europe/London, Europe/Berlin, America/New_York,
   Asia/Tokyo). Alle späteren Snapshots für Features ignorieren.
2. **Parsing:** `outcomePrices`/`clobTokenIds` doppelt JSON-dekodieren; String-Zahlen casten;
   Bucket-Label-Parser mit den 4 Mustern (inkl. NYC-2°F-Bändern).
3. **Cross-File-Ground-Truth-Join (D3):** Archive-Werte über alle späteren Dateien sammeln,
   jüngster Abruf gewinnt, nur Stations-Koordinaten; half-up-Rundung; Bucket-Zuordnung nativ-ganzzahlig.
4. **QS-Flags:** Overround-Ausreißer (>0,10), Teiltage, `hours_to_event_end`-Plausibilität.
5. **Schreiben:** idempotenter Full-Rebuild → `data/processed/silver.duckdb` (Tabelle
   `market_bucket_daily`) + Parquet-Export partitioniert nach `city`. Raw bleibt unberührt.
6. **📌 Ingestion-Erweiterung (aus D4):** Resolution-Fetcher — am Folgetag `GET /events?slug=`
   für Vortages-Events, Antwort append-only nach `data/raw/polymarket/resolutions_<D>.ndjson`.
   Füllt `market_resolved_bucket`/`labels_agree` vorwärts.

Erwartete Ausgabegröße v1 (nur live): ~950 Zeilen; mit AP 1.3-Backfill ~5 600 Zeilen.
