# Abgabeplan — Endspurt (Stand Fr, 14.08.2026)

> Ersetzt die Wochenplanung des Projektplans für die verbleibende Zeit.
> **Auslöser:** Konsultationshinweis des Prüfers — bewertet werden vorrangig
> **Umsetzung, Aufbau und Architektur der Pipeline**, nicht die Analyseergebnisse.
> Die Gliederung wurde entsprechend umgebaut (`docs/arbeit/00_gliederung.md`, Fassung 2).

## Ausgangslage

| | |
|---|---|
| Technik (Pipeline, Betrieb, Modelle) | ✅ fertig, läuft seit 57 Tagen autonom |
| Material (Notizen, Ergebnis-/Incident-Docs, Lineage) | ✅ vollständig vorsortiert |
| Text | ⚠️ 669 / 2.000 W (33 %) — Abschnitte 2 und 3 |
| Data Freeze | ❌ offen (Pipeline sammelt noch) |
| Code-Anhang, Gesamtdokument | ❌ offen |

**Zu schreiben: ~1.330 Wörter in 5 Arbeitsschritten.** Nichts davon muss neu
erarbeitet werden — alle Inhalte liegen belegt im Repo.

---

## Arbeitspakete (in dieser Reihenfolge abarbeiten)

### AP F1 — Data Freeze (~15 Min) 🧊
Finaler `git pull`; `build_silver.py` + `build_features.py`; beide Analyse-Skripte
(`ap33_logreg.py`, `ap41_gbm.py`) auf dem Freeze-Stand. Ergebnis-JSONs als
Freeze-Referenz sichern (Ausnahme vom `data/processed`-Ignore, damit die Zahlen der
Arbeit reproduzierbar belegt sind). Kennzahlenblock für die `[Z: …]`-Marker erzeugen.
**Ergebnis:** eingefrorene Zahlenbasis; ab hier ändert sich nichts mehr.

### AP F2 — Abschnitt 4 „Transformation & Datenmodell" (350 W) ⭐
**Der wichtigste neue Abschnitt** — Kern dessen, was der Prüfer sehen will.
Grain · As-of-Cut als Leakage-Schutz · Label-Definition + Revision · Normalisierung
(Einheiten, Bucket-Parser, Dedup) · Idempotenz + eingebaute QS-Abbrüche · Lineage.
**Quellen:** `cleaned_schema_AP1.1.md`, `DECISIONS_AP1.1–1.3`, `build_silver.py`.

### AP F3 — Abschnitt 5 „Betriebskonzept" (450 W)
Fünf Säulen mit Ist-Implementierung; PDRP an drei realen Vorfällen; 8/8
Resilienz-Nachweise; Restrisiken.
**Quellen:** `betriebskonzept_notizen.md`, `alerting_konzept.md`, beide Incident-Docs.

### AP F4 — Abschnitt 3 ergänzen (+90 W) & Abschnitt 6 „Ergebnisse" (130 W)
Ingestion um Umsetzungsdetails erweitern (Retry/Backoff, Trigger-Redundanz,
Rotation/Partitionierung, Idempotenz des Resolution-Fetchers). Ergebnisse **bewusst
knapp**: Korpusumfang, Evaluationsaufbau in zwei Sätzen, eine Kernaussage;
Vergleichstabelle in den Anhang.

### AP F5 — Abschnitt 1 „Einleitung" (150 W) & Abschnitt 7 „Fazit" (120 W)
Zum Schluss geschrieben, damit sie zum fertigen Text passen.

### AP F6 — Zusammenbau & Abgabe-Paket
Alle `[Z: …]`-Marker gegen Freeze-Zahlen ersetzen; Abschnitte zu einem Dokument
zusammensetzen; Wortzahl final prüfen (Ziel 2.000 ± 5 %); Code-Anhang
zusammenstellen (Auszüge + Schema-/Lineage-/Vergleichstabelle);
Übergabe an den Verfasser für Formatierung, Zitation und PDF-Export.

---

## Offene Punkte für den Verfasser

- **Abgabetermin bestätigen:** „morgen" = Sa 15.08.; der Projektplan nannte den 16.08.
- **Abgabeformat** (Word/PDF/LaTeX) — der Text entsteht als Markdown und braucht einen
  Konvertierungsschritt.
- **Eigenleistung:** Alle Abschnitte sind belegte Rohfassungen und müssen vom Verfasser
  durchgesehen, sprachlich angeeignet und verantwortet werden
  (Eigenständigkeitserklärung); Zitation/Quellenverzeichnis liegen beim Verfasser.
