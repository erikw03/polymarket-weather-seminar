# Raw-Inspektionsreport — AP 1.1 (Phase A)

**Stand:** 2026-07-10, Korpus bis Snapshot `2026-07-10T08:02Z` (Commit `1d7b86a`).
**Methode:** vier read-only Inspektionsskripte (Standardbibliothek, deterministisch) unter
`scripts/inspect/01…04_*.py`; jede Zahl in diesem Report ist damit reproduzierbar:

```bash
.venv/bin/python scripts/inspect/01_corpus_overview.py
.venv/bin/python scripts/inspect/02_schema_inventory.py
.venv/bin/python scripts/inspect/03_asof_quality.py
.venv/bin/python scripts/inspect/04_drilldown_leakage_overround.py
```

Legende Vorbefund-Abgleich: ✅ bestätigt · ⚠️ teilweise / mit Einschränkung · ❌ widerlegt · ➕ Erweiterung (im Vorbefund nicht enthalten)

---

## 1. Ablage & Umfang

| Quelle | Pfad | Dateien | Zeitspanne | Zeilen | Volumen |
|---|---|---|---|---|---|
| Wetter | `data/raw/weather/weather_YYYY-MM-DD.ndjson` | 22 | 2026-06-16 … 2026-07-10 | 5 010 | ~3,5 MB |
| Polymarket | `data/raw/polymarket/polymarket_YYYY-MM-DD.ndjson` | 22 | 2026-06-16 … 2026-07-10 | 2 520 | ~350 MB |

- ✅ Tagesrotierende NDJSON-Dateien, 1 Zeile = 1 API-Abruf (Wetter: 1 Zeile je Stadt × kind; Markt: 1 Zeile je Stadt).
- ➕ **Kalenderlücke 2026-06-17 … 2026-06-19** (Dateiebene): Sammelbeginn 16.06. war ein Einzeltest; durchgehende Sammlung erst ab 20.06. (lokal) bzw. 21.06. (Cloud-Cron). Randtage 06-16/06-20/07-10 sind Teiltage.
- ➕ **Dritter `kind` existiert:** `weather-historical-forecast` (genau 1 Record, München, 20.06.) — ein manueller Forecast-Backfill für 16.–19.06. Muss im Transform explizit behandelt (oder bewusst ignoriert) werden.
- ➕ **Zusatzbestand `data/backfill/`** (8 konsolidierte JSONs, Stand 21.06.): je Stadt aufgelöste Alt-Märkte inkl. **resolved_bucket** und stündlicher Preis-Historie (London 109, München 105, NYC 109, Tokio 100 = **423 aufgelöste Zieltage, 2026-03-01 … 2026-06-20**) plus Wetter-Historien (112 Tage forecast+archive). Für die Label-Diskussion (D3/D4) hochrelevant.
- ✅ 4 Städte: London, Munich, NYC, Tokyo (keine weiteren im Korpus).

## 2. Schema-Inventar

**Wetter** (je Zeile `{_meta, response}`): ✅ wie im Vorbefund. `response.daily` mit parallelen Arrays `time[]`, `temperature_2m_max[]`, `temperature_2m_min[]` + `daily_units`; dazu `latitude/longitude/elevation/timezone/utc_offset_seconds/generationtime_ms`. Vollständige Feldliste mit Typ/Präsenz/Beispiel: Output von Skript 02.
- ⚠️ `_meta` hat **zwei Varianten**: 4 999 Records mit `station` + `temperature_unit`, **11 alte Records ohne** (16.06. + früher 20.06.). Für diese 11 gilt zusätzlich: **München-Koordinaten = Stadtzentrum (48.14, 11.58)** statt Flughafen (48.3538, 11.7861). → Transform braucht Fallback (Unit aus Stadt-Konfig) bzw. Ausschlussregel.

**Polymarket** (je Zeile `{_meta, gamma_events, clob_quotes}`):
- ➕ **Top-Level-Key `clob_quotes` in 100 % der Zeilen** (im Vorbefund nicht erwähnt): je Yes-Token `midpoint.mid`, `price_buy.price`, `price_sell.price` — als **String-Zahlen**. Zweite, orderbuch-basierte Preisquelle neben `outcomePrices`.
- Event-Ebene (n=6 383 Event-Snapshots): ✅ Felder wie vermutet, plus ➕ `eventDate` (direktes Zieltagsfeld, immer vorhanden — besser als `endDate`-Parsing), ➕ `resolutionSource` (Wunderground-URL je Event), ➕ `eventMetadata.context_description` (98,8 %; von Polymarket mitgelieferter Prognose-Kontexttext), `series/tags/…`.
- Market/Bucket-Ebene (n=70 213 Bucket-Snapshots): ✅ `groupItemTitle`, `outcomes`/`outcomePrices`/`clobTokenIds` als **JSON-Strings** (doppelt dekodieren), `volume`/`liquidity` teils String, teils Zahl (`volumeNum`, `liquidityNum` als numerische Duplikate). ➕ Resolution-Felder: `umaResolutionStatus` (0,6 %), `closedTime` (0,1 %), `automaticallyResolved` (0,1 %), `closed` (bool, immer).
- ⚠️ Typen-Mix beachten: mehrere Felder `float/int` gemischt; Preise/Volumina teils String → Silver muss casten.

## 3. Duplikate & Abruffrequenz

- ⚠️ **~30–35 Abrufe/Stadt/Tag** an vollen Tagen (nicht ~28): seit 21.06. laufen **zwei redundante Trigger** (GitHub-`schedule` + externer Cron), manche Stunden haben daher 2 Abrufe. Verteilung (Skript 01): volle Tage 28–35, Randtage weniger.
- ❌ **„Archive-Werte über alle Abrufe identisch" gilt nicht streng:** 32 von 112 (city × target_date)-Paaren haben >1 unterschiedliche Max-Werte. Zwei Ursachen:
  1. **ERA5-Revisionen** ±0,1–0,3 °C (z. B. London 01.07.: 25,1 → 25,4),
  2. **Koordinatenwechsel München** am 20.06. (Stadtzentrum→Flughafen): München 14.06. = **19,7 vs. 21,2 °C** (1,5 °C!).
  → Dedup-Regel darf nicht „beliebigen" Wert nehmen, sondern muss definieren: *jüngster Abruf gewinnt* (+ nur Flughafen-Koordinaten).
- ✅ Forecast intraday variabel, Preise intraday variabel (Belege unter 4.).

## 4. As-of-Variabilität (quantifiziert)

**Forecast-Max je (Stadt × Zieltag)** über alle Snapshots (94 Zieltage mit ≥2 Snapshots; native Einheit):
Spannweite mean **3,6**, median **2,8**, p90 **7,9**, max **17,6** (NYC 26.06., 76,8 °F → 83,1 °F über 3 Tage).
Beispiel-Zeitreihe im Skript-03-Output.

**Bucket-Yes-Preis je (Stadt × Zieltag × Bucket)** (990 Zeitreihen ≥2 Snapshots):
Spannweite mean **0,197**, median **0,064**, p90 **0,659**, max **0,997**.

→ ✅ Die As-of-Dimension ist real und groß. **Welcher Snapshot „der" Tageswert ist, ist die zentrale Design-Entscheidung (D2)** — sie verändert Feature UND faire Vergleichbarkeit Modell vs. Markt.

## 5. Ground-Truth-Verfügbarkeit (datei-übergreifender Join)

- ✅ Ist-Max für Zieltag D erscheint in Archive-Fenstern der Folgedateien. Lag-Verteilung „erster Ist-Wert": **D+1 für 81 von 112**, D+0 für 4 (Tokio, Zeitzoneneffekt), Rest D+2…D+7 (Backfill-Fenster der Randtage).
- ✅ **Abdeckung 100 %:** alle vergangenen Markt-Zieltage haben einen Open-Meteo-Ist-Wert (London 20/20, München 23/23, NYC 20/20, Tokio 19/19 = **82 label-bare Zieltage** im Live-Korpus; + 423 im Backfill-Bestand).
- Keine Null-Zellen im Archive (0 von allen geprüften Arrays).

## 6. Roll-off & Resolution

- ✅ **Event-Ebene: kein einziger `closed=true`-Snapshot** (0 von 6 383) — der Collector filtert bewusst auf offene Events (Ingestion-Design). Aufgelöste Events verschwinden aus dem Feed.
- ⚠️ **Aber differenzierter als der Vorbefund:**
  - Events bleiben **weit über `endDate` (12:00Z) hinaus** mit `closed=false` sichtbar: letzte Sichtung meist 15Z (18×), 22–23Z (39×) oder sogar D+1 (20×).
  - Auf **Bucket-Ebene** gibt es Resolution-Spuren: `umaResolutionStatus` „proposed" (337 Snapshots) / „resolved" (70 Snapshots, 7 Events), inkl. `closedTime` (Beispiel London 22.06., 23:41Z).
- ➕ **Leakage-Beleg** (Skript 04, London 22.06., Gewinner-Bucket 27 °C): Yes-Preis 09:01Z = **0,40** → 13:01Z = **0,90** → 16:01Z = **0,997** → 19:01Z = **1,0**. Nach dem lokalen Tageshöchststand ist der Preis faktisch das Label. **Snapshots nach ~Zieltag-Vormittag dürfen nie ins Feature.**
- ➕ Konsequenz fürs Label: das *im Feed sichtbare* „resolved" ist selten und unzuverlässig; belastbare Auflösung liefert (a) der Backfill-Bestand (423 resolved) bzw. (b) das Wetter-Archiv. **To-do AP 1.2/1.3 (Ingestion):** aufgelöste Events gezielt per Slug nachziehen (`/events?slug=…` liefert `outcomePrices ["1","0"]` je Bucket), statt sich auf den Live-Feed zu verlassen.

## 7. Einheiten & Stationen

| Stadt | Wetter-Unit (`_meta`) | Markt-Bucket-Unit | Wetter-Koordinaten | Markt-`resolutionSource` |
|---|---|---|---|---|
| London | celsius | °C (19 393 Buckets) | 51.5048, 0.0495 | wunderground …/gb/london/**EGLC** (City Airport) |
| Munich | celsius (11× fehlend) | °C (19 173) | 48.3538, 11.7861 (11× alt: 48.14, 11.58) | …/de/munich/**EDDM** (Flughafen) |
| NYC | fahrenheit | °F (14 784) | 40.7769, −73.8740 | …/us/ny/new-york-city/**KLGA** (LaGuardia) |
| Tokyo | celsius | °C (16 863) | 35.5494, 139.7798 | …/jp/tokyo/**RJTT** (Haneda) |

- ✅ Einheiten je Stadt konsistent zwischen Markt und Wetter; **NYC durchgehend °F** — zusätzlich sind NYC-Buckets **2-Grad-Bänder** („32-33°F") statt 1-Grad (°C-Städte), plus offene Ränder („or below/or higher"). Bucket-Parsing muss 4 Labelmuster können.
- ✅ Wetter-Koordinaten zeigen seit 20.06. auf die jeweilige **Auflösungsstation** (Flughafen). ⚠️ Quellen-Mismatch bleibt trotzdem: Open-Meteo modelliert (Grid/Reanalyse), Wunderground misst die Station — im Backfill-Vergleich lag die Differenz je Stadt im Mittel bei ~0,5–1 °C (Station−ERA5: München +1,06, NYC −0,71). Muss als Label-Vorbehalt dokumentiert werden.

## 8. Datenqualität & Anomalien

| Prüfpunkt | Befund |
|---|---|
| kaputte JSON-Zeilen | **0** (7 530 Zeilen geprüft) |
| leere `gamma_events` | **0** |
| `outcomePrices`-Parse-Fehler | **0** von 70 213 |
| Event-Titel ≠ `_meta.city` | **0** |
| Archive-Null-Zellen | **0** |
| `_meta` ohne `temperature_unit`/`station` | **11** Wetter-Records (16.06./20.06.) |
| Summe Yes-Preise (Overround) | mean **1,023**, median **1,024** ✅ (~1.03-Hypothese) |
| Overround-Ausreißer (Summe <0,9 od. >1,1) | **116 von 6 383 (1,8 %)**, bis **4,59** |

- ➕ **Overround-Ausreißer sind frisch gelistete Märkte** (Zieltag D+2, Listing-Morgen): mehrere Buckets stehen auf Platzhalter-Quotes (~0,5), z. B. München 12.07. am 10.07. 04:14Z mit Summe 4,59. → Silver braucht eine Qualitätsregel (z. B. Snapshot verwerfen/flaggen, wenn |Summe−1| > Schwelle) **oder** Preise je Snapshot auf Summe 1 normalisieren + Flag.
- ➕ Zeitzonen-Effekt bestätigt: Dateitag = UTC-Abruftag; NYC-Zieltag endet 04:00Z des Folgetags; Tokio-Ist erscheint teils schon am „selben" UTC-Tag. Join-Logik muss Zieltag (lokal) von Abrufzeit (UTC) sauber trennen — `eventDate` (Markt) bzw. `daily.time` (Wetter, lokale Kalendertage) sind die verlässlichen Zieltag-Schlüssel.
- ➕ Preis-/Volumenfelder teils als String (`outcomePrices`, `volume`, `liquidity`, CLOB-Quotes) → Cast-Regeln nötig; `volumeNum`/`liquidityNum` existieren als numerische Alternativen.

---

## Vorbefund-Abgleich (Kurzfassung)

| Vorbefund | Status |
|---|---|
| NDJSON-Struktur, `_meta`+`response` / `_meta`+`gamma_events` | ✅ (➕ `clob_quotes` überall) |
| 2 kinds Wetter | ⚠️ 3 kinds (1× `weather-historical-forecast`) |
| ~28 Abrufe/Stadt/Tag | ⚠️ 28–35 (Doppel-Trigger seit 21.06.) |
| Archive-Werte je Tag identisch | ❌ 32/112 Paare variieren (Revisionen + München-Koordinatenwechsel) |
| Forecast/Preise intraday variabel („as-of") | ✅ quantifiziert (Median-Spannweite 2,8 Einheiten bzw. 0,064 Preis) |
| Einheiten gemischt, NYC=°F | ✅ (➕ NYC-Buckets sind 2°F-Bänder) |
| Ground Truth datei-übergreifend, D+1 | ✅ (Lag meist 1 Tag, Abdeckung 100 %) |
| Roll-off: resolved verschwindet, kein closed-Snapshot | ⚠️ Event-Ebene ja; Bucket-Ebene enthält 70 resolved-Snapshots; Events bis zu D+1 sichtbar; Preis nach 12Z ≈ Label (Leakage!) |
| Overround ~1,03 | ✅ (➕ 1,8 % Ausreißer bei frischen Listings) |
| Quellen-Mismatch Wunderground vs. Open-Meteo | ✅ (Koordinaten zeigen immerhin auf die Station; Differenz ~0,5–1 °C) |
