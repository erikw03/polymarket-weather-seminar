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
| (folgt) | | |
