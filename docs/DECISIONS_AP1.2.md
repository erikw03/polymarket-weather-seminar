# Entscheidungs- & Änderungslog — AP 1.2 (Transform Raw→Cleaned)

> Fortsetzung von `DECISIONS_AP1.1.md`. Umsetzung des freigegebenen Schemas
> (`docs/cleaned_schema_AP1.1.md`) — keine neuen Design-Entscheidungen ohne Doku hier.

## Rahmen

- **Datum:** 2026-07-10/11 (AP 1.2 laut Projektplan: Fr 11.07.)
- **Scope:** (1) Resolution-Fetcher (Ingestion-Erweiterung aus D4), (2) Transform
  Raw→Silver nach Schema, (3) Verifikation. Raw bleibt WORM — der Transform liest nur;
  der Fetcher schreibt ausschließlich **neue** append-only Dateien (`resolutions_<D>.ndjson`).
- **Milestone:** erste Cleaned-Tabelle (`market_bucket_daily`) existiert in DuckDB + Parquet.

## Umsetzungs-Entscheidungen (innerhalb des freigegebenen Schemas)

- **U1 Ein-Datei-Transform `build_silver.py`** (Repo-Root, wie `run_ingestion.py`):
  für die Seminararbeit lesbarer als ein Paket; klare Abschnitts-Kommentare je Schema-Regel.
  Der Juni-Prototyp `build_processed.py` bleibt unangetastet liegen (Historie), wird aber im
  README als „ersetzt durch build_silver.py" markiert.
- **U2 Resolution-Fetcher idempotent über Bestandscheck:** vor jedem Fetch werden vorhandene
  `resolutions_*.ndjson` gescannt; ein Event wird nur geholt, wenn noch **kein aufgelöster**
  Datensatz (event.closed=true) existiert. Noch-nicht-aufgelöste Events werden NICHT
  geschrieben (kein Müll, automatischer Retry beim nächsten Lauf). Lookback 4 Tage im
  Normalbetrieb; einmaliger Init-Backfill ab 2026-06-20 (Beginn Live-Korpus).
- **U3 Fetcher speichert das rohe Event verbatim** (Raw-Zone-Prinzip: nicht interpretieren;
  Gewinner-Ableitung passiert erst im Transform).
- **U4 Rundung half-up via `decimal.ROUND_HALF_UP`** (Python-`round()` wäre Banker's Rounding
  — widerspräche der freigegebenen D3-Regel).
- **U5 `flag_partial_day` datengetrieben:** Teiltag = Polymarket-Tagesdatei mit < 50 % der
  Median-Zeilenzahl, plus der letzte (noch laufende) Sammeltag. Vermeidet hartkodierte Daten.
- **U6 Legacy-Ausschluss fürs Label über `station`-Feld:** die 11 Alt-Records (16./20.06.,
  z. T. München-Stadtzentrum) haben kein `_meta.station` → Kriterium `station vorhanden`
  schließt genau sie aus (deckungsgleich mit „nur Stations-Koordinaten" aus D3).
- **U7 Ein Parse-Durchlauf über die 350 MB Markt-Raw** mit „latest-vor-Cut gewinnt"-Auswahl
  im Speicher (statt zwei Pässen); `fetched_at` wird explizit verglichen, nicht Dateireihenfolge
  angenommen (Doppel-Trigger kann leicht out-of-order sein).

- **U8 As-of nur für begonnene Zieltage:** Zeilen entstehen erst, wenn der D2-Cut in der
  Vergangenheit liegt (sonst wäre „letzter Snapshot vor Cut" bei jedem Lauf ein anderer —
  Reproduzierbarkeit). Zukünftige Events (D+1/D+2 im Feed) erscheinen also noch nicht im Silver.

## Arbeitsschritte-Protokoll

| # | Schritt | Ergebnis |
|---|---|---|
| 1 | Log angelegt | diese Datei |
| 2 | Resolution-Fetcher gebaut | `src/ingest_resolutions.py`, in `run_ingestion.py` integriert |
| 3 | Init-Backfill Resolutions | 84 aufgelöste Events (20.06.–10.07.) → `resolutions_2026-07-11.ndjson`; 2. Lauf: 0 neu (idempotent ✓) |
| 4 | Transform gebaut | `build_silver.py` (Schema 1:1, Ein-Pass-Auswahl, QS-Checks eingebaut) |
| 5 | Transform-Lauf | **946 Zeilen**, 86 Zieltage, 0 PK-Duplikate, 0 Label-Fehler, max. Normierungsfehler 3e-16 |
| 6 | E2E-Ingestion-Test | `run_ingestion.py` mit 3. Quelle fehlerfrei, Resolutions idempotent |
| 7 | Verifikation Inhalt | Stichprobe München 05.07. plausibel; `labels_agree` quantifiziert (s. Befund) |

## QS-Ergebnisse des ersten Laufs

- `min_hours_to_event_end` = 8,0 h — **kein** Leck: das ist NYC (Mitternacht lokal = 04:00Z,
  `endDate` 12:00Z ⇒ konstruktiv 8 h). Der Cut liegt per Definition vor Beginn des lokalen
  Zieltags; der Audit-Wert ist stadtabhängig (Tokio ≥ 21 h, München ≥ 14 h, London ≥ 13 h).
- `flag_overround_outlier`: 11 Zeilen (1 Münchner Zieltag mit frischem Listing als as-of) — Flag wirkt.

## ⚠️ Befund: Label-Quellen-Mismatch ist GRÖSSER als in AP 1.1 angenommen

`labels_agree` (Open-Meteo-Bucket vs. offizielles Markt-Ergebnis, 79 Tage):
exakt gleich nur **23 %** (18/79); ±1 Grad: 57 %. Systematischer Versatz je Stadt
(Gewinner-Bucket − Open-Meteo-Ist, nativ): **München +2,0**, Tokio +0,5, NYC +0,3, London −0,3.
Bei 1-Grad-Buckets macht schon ~1 °C Bias das Open-Meteo-Label meist „falsch" relativ zum
offiziellen Ergebnis. → Entscheidungsvorlage **D3-Revision** an den Auftraggeber (STOPP):
offizielles Markt-Ergebnis (jetzt via Resolution-Fetcher zu ~100 % verfügbar, vorwärts
selbsttragend) als **primäres** Label; Open-Meteo-Ist bleibt Feature/Zusatzspalte.
Bis zur Freigabe bleibt der Transform wie freigegeben (D3 unverändert).

## ✅ D3-Revision — freigegeben (2026-07-12, „Freigabe für alle 3 (a bis c)")

- (a) **umgesetzt:** neue Spalte `label_is_winner_official` = primäres Label
  (Bucket = offizielles Gewinner-Bucket); QS-Check „genau 1 offizieller Gewinner je
  aufgelöstem Tag" ergänzt; `label_source` dokumentiert beide Quellen.
- (b) Open-Meteo-Label (`label_in_bucket`) bleibt als Sekundär-/Vergleichsspalte —
  der Mismatch (23 % exakt, München +2 °C) ist quantifizierte Limitation fürs
  Datenqualitäts-Kapitel der Arbeit.
- (c) Detail-Zahlen vorgelegt (Tag-für-Tag-Vergleich + Verteilung; siehe Chat/
  Skript-Queries): London 5/20, München 1/20, NYC 6/20, Tokio 7/19 exakt;
  Versatz mean: LON −0,3 / MUC +2,0 / NYC +0,3 / TYO +0,5 (nativ).
- Schema-Doc entsprechend revidiert (Status-Block + D5-Tabelle + Lineage).
- Zweiter Transform-Lauf nach `git pull` (Korpus 12.07.): **1 001 Zeilen, 91 Zieltage,
  88 offizielle Gewinner, alle QS-Checks grün.** Nebenbefund: der Resolution-Fetcher
  lief bereits autonom in der Cloud (resolutions_2026-07-12.ndjson ohne manuelles Zutun).

## Offene Punkte

- 📌 AP 1.3: Backfill-Bestand (`source='backfill'`) einspielen; Forecast-Lücke 17.–19.06. prüfen.
- 🔍 AP 2.x: `official_known`-Quote als Freshness-Check (Resolutions hängen ~1–2 Tage nach — normal).
