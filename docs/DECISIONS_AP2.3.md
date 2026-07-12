# Entscheidungs- & Änderungslog — AP 2.3 (Pipeline härten / Fehlertoleranz)

> Plan: Retry/Backoff prüfen, Idempotenz testen, bewusst Fehler simulieren (API down).
> Meilenstein: Pipeline überlebt Ausfälle sauber. Plus Übergabe aus AP 2.2:
> Quality-Gate im Actions-Workflow.

## Design-Entscheidungen

- **U1 Simulation ohne Seiteneffekte:** API-Ausfälle werden über `httpx.MockTransport`
  injiziert (kein Netz nötig, deterministisch); Schreib-Tests laufen gegen Temp-Verzeichnisse
  (Umbiegen der `config.RAW_*`-Pfade im Testprozess). **Das echte Raw wird nie berührt** (WORM).
- **U2 Testskript wird versioniert** (`scripts/harden/test_resilience.py`): die Härtungs-Nachweise
  sind reproduzierbar, nicht einmalige Chat-Behauptungen. Wiederholbar via
  `python scripts/harden/test_resilience.py` (Exit 0 = alle Nachweise bestanden).
- **U3 Gefundene Schwachstelle wird gefixt, nicht wegdokumentiert:** Der Transform brach bei
  einer einzigen korrupten NDJSON-Zeile komplett ab (json.loads ungeschützt). Fix: tolerante
  Leser-Funktion `iter_ndjson()` (überspringt + zählt korrupte Zeilen, loggt WARN); neuer
  QS-Abbruch nur, wenn > 0,5 % der Zeilen korrupt sind (Schwelle dokumentiert: einzelne
  kaputte Zeile = überspringbar; systematische Korruption = FAIL).
- **U4 Quality-Gate NACH dem Daten-Commit im Workflow:** Reihenfolge Ingestion → Commit →
  Silver-Build → quality_checks. Begründung: ein rotes Gate darf die Persistenz der (validen)
  Rohdaten nicht verhindern — das Gate schützt die Sichtbarkeit von Qualitätsproblemen
  (rote Runs + GitHub-Mail = P1-Pfad aus dem Alerting-Konzept), nicht die Datensammlung.
- **U5 Idempotenz-Definition:** identisch modulo Lauf-Metadaten (`created_at`; 
  `transform_version` ist bei gleichem Commit gleich). Nachweis über Zeilenzahl + Checksumme
  über fachliche Spalten bei zwei aufeinanderfolgenden Läufen.

## Arbeitsschritte-Protokoll

| # | Schritt | Ergebnis |
|---|---|---|
| 1 | Log angelegt | diese Datei |
| 2 | Schwachstelle gefixt (U3) | `iter_ndjson()` in `build_silver.py`: korrupte Zeile → skip+count+WARN; Abbruch erst > 0,5 % (vorher: 1 kaputte Zeile = Totalabsturz des Transforms) |
| 3 | Resilienz-Testsuite gebaut | `scripts/harden/test_resilience.py` (T1–T8, MockTransport + Temp-Dirs, Raw unberührt) |
| 4 | Suite ausgeführt | **8/8 Nachweise bestanden** (Protokoll unten) |
| 5 | Quality-Gate in CI (U4) | 2 neue Workflow-Steps nach dem Daten-Commit; Verifikationslauf grün |

## Nachweise (T1–T8, alle bestanden)

| # | Nachweis | Ergebnis |
|---|---|---|
| T1 | 2× HTTP 500 → Erfolg im 3. Versuch | ✓ Retry greift nur bei transienten Fehlern |
| T2 | HTTP 404 → sofortiger Fehler, 1 Versuch | ✓ Client-Fehler werden nicht sinnlos retried |
| T3 | API dauerhaft down → 5 Versuche, dann Original-Exception | ✓ begrenzter Backoff, kein Endlos-Loop |
| T4 | HTTP 429 → retried | ✓ Rate-Limits werden abgewartet |
| T5 | Wetter-Quelle crasht → Polymarket läuft weiter, Exit 0 | ✓ Quellen-Isolation |
| T6 | Beide Quellen down → Exit 1 | ✓ Alarm-Pfad (cron sieht Fehler) |
| T7 | korrupte NDJSON-Zeile → übersprungen + gezählt, kein Crash | ✓ Fix aus U3 wirkt |
| T8 | Transform 2× → identische Zeilenzahl + Checksumme | ✓ Idempotenz (5 468 Zeilen, hash-gleich) |

## Meilenstein

✅ **„Pipeline überlebt Ausfälle sauber"** — belegt durch reproduzierbare Testsuite statt
Behauptung; plus Quality-Gate live in CI (stündlich, FAIL = roter Run = Mail-Alarm).

## Übergabe an AP 2.4 (Lineage-Doku + Betriebskonzept-Notizen)

- Lineage-Tabelle existiert bereits (`cleaned_schema_AP1.1.md`); AP 2.4 konsolidiert sie mit
  den Betriebs-Bausteinen (Alerting-Konzept, Härtungs-Nachweise, Architektur-Notizen) zu
  den finalen Betriebskonzept-Notizen für die Arbeit.
- Woche-2-Meilenstein („Betrieb steht") ist nach AP 2.4 fällig.
