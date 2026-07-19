# Entscheidungs- & Änderungslog — AP 2.4 (Lineage-Doku + Betriebskonzept-Notizen)

> Plan: Data Lineage dokumentieren (welches Feld kommt woher), Betriebskonzept-Bausteine
> sammeln. Meilenstein: Woche-2-Abschluss „Betrieb steht, Material für Arbeit gesammelt".

## Design-Entscheidungen

- **U1 Keine Duplikation:** Feld-Lineage (Spalte → Raw-Feld → Regel) existiert bereits
  vollständig in `cleaned_schema_AP1.1.md`. Das neue `docs/lineage.md` ergänzt die
  **System-Ebene** (Quelle → Endpoint → Datei → Artefakt) und verweist auf die Feld-Tabelle,
  statt sie zu kopieren (eine Wahrheit, ein Ort).
- **U2 Lineage muss demonstrierbar sein, nicht nur dokumentiert:** neues read-only Werkzeug
  `scripts/inspect/05_trace_lineage.py` — nimmt (Stadt, Zieltag, Bucket) und druckt die
  komplette Herkunftskette einer Silver-Zeile: Silver-Werte → exakte Raw-Zeile des
  Markt-Snapshots → Forecast-Zeile → Archiv-Zeile (Label) → Resolutions-Zeile. Beleg für
  die Arbeit, dass Auditierbarkeit real funktioniert (nicht nur Architektur-Behauptung).
- **U3 Betriebskonzept-Notizen als Kapitel-Skelett:** `docs/betriebskonzept_notizen.md`
  strukturiert das vorhandene Material (Alerting-Konzept, Härtungs-Nachweise, QS-Module,
  Vorfalls-Historie) entlang der späteren ~1.200-Wörter-Gliederung von AP 5.1 — sammeln
  UND vorsortieren, damit das Schreiben nur noch Ausformulieren ist.

## Arbeitsschritte-Protokoll

| # | Schritt | Ergebnis |
|---|---|---|
| 1 | Log angelegt | diese Datei |
| 2 | Lineage-Tracer gebaut (U2) | `scripts/inspect/05_trace_lineage.py`; Beispiel München 05.07./24°C: alle 4 Herkunfts-Zeilen gefunden (Datei + Zeilennr.) |
| 3 | `docs/lineage.md` | System-Datenfluss, Quellen-Register, Zeilen-Rückverfolgung, Lineage-Vorfälle |
| 4 | `docs/betriebskonzept_notizen.md` | Kapitel-Skelett K1–K5 mit Belegen + Kennzahlenblock |

## Meilenstein

✅ **Woche-2-Abschluss „Betrieb steht, Material für Arbeit gesammelt":**
Betrieb läuft vollautomatisch mit Gate + Alerting-Pfad; Lineage ist dokumentiert UND
demonstrierbar; das Betriebskonzept-Kapitel ist als belegtes Skelett vorbereitet.

## Übergabe an Woche 3 (AP 3.1: Analysis-Zone & Feature-Engineering)

- Gold-Zone aus Silver ableiten: Feature-Tabelle (Forecast-Werte, Differenzen,
  Vortageswerte, Saisonalität) + ML-ready Splits (zeitlich sortiert).
- `source` und `flag_*` als Kontroll-/Ausschluss-Variablen mitführen.
- Baselines stehen konzeptionell: Marktpreis-als-Prädiktor + naive Forecast-Regel.
