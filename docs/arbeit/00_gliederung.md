# Detail-Gliederung der Seminararbeit — **Fassung 2 (14.08.)**

**Thema:** Datenpipeline & -korpus aus Wetterprognose- und Prognosemarktdaten
**Umfang:** 2.000 Wörter netto + Code als Anhang (zählt nicht mit)

> **Umbau gegenüber Fassung 1 (30.07.) — Grund: Konsultationshinweis des Prüfers.**
> Bewertet werden vorrangig **Umsetzung, Aufbau und Architektur der Pipeline**,
> nicht die Analyseergebnisse. Konsequenzen:
> 1. Ergebnisse von 400 → **130 W** (nur noch Kernaussage, keine Metrik-Diskussion).
> 2. Neuer eigener Abschnitt **4 „Transformation & Datenmodell"** (350 W) — die
>    Kern-Umsetzungsentscheidungen (Grain, As-of-Cut, Label, Idempotenz) waren bisher
>    auf andere Abschnitte verteilt und damit unterrepräsentiert.
> 3. Ingestion & Speicherung 350 → 400 W, Betriebskonzept 450 W (bleibt tragend).
> → **Pipeline-Kapitel (2–5) = 1.600 W = 80 %** der Arbeit.

Legende: ✍️ geschrieben · 🔄 zu ergänzen · ⬜ offen

| # | Abschnitt | Budget | Ist | Status |
|---|---|---|---|---|
| 1 | Einleitung & Use-Case | 150 | – | ⬜ |
| 2 | Vorgehen & Architektur | 400 | 352 | ✍️ |
| 3 | Ingestion & Speicherung | 400 | 403 | ✍️ |
| 4 | **Transformation & Datenmodell** *(neu)* | 350 | 325 | ✍️ |
| 5 | Betriebskonzept: Observability & Fehlertoleranz | 450 | 383 | ✍️ |
| 6 | Ergebnisse *(kompakt)* | 130 | 116 | ✍️ |
| 7 | Fazit & Ausblick | 120 | – | ⬜ |
| | **Summe** | **2.000** | **1.579** | 79 % |

---

## 1 — Einleitung & Use-Case (150 W → **auf ~200 W erhöht**, s. Hinweis unten)

Prognosemärkte als Informationsaggregatoren; Fragestellung: Wie gut tracken
Polymarkets implizite Wahrscheinlichkeiten für Tages-Höchsttemperaturen Prognose und
Ergebnis? **Betonung auf dem Data-Engineering-Ziel:** Aufbau eines belastbaren,
auditierbaren Korpus als Voraussetzung jeder Analyse. Abgrenzung: read-only, kein Handel.

**Modulbezug:** CRISP-DM *Business Understanding* (K1). **Belege:** `README.md`.

## 2 — Vorgehen & Architektur (400 W) ✍️ *fertig*

CRISP-DM iterativ mit zwei belegten Rückkopplungen (Leakage-Befund → As-of-Cut;
Label-Mismatch → Quellenwechsel). Medallion Bronze→Silver→Gold. 4 V's als
Dimensionierungsbegründung, *Veracity* als Projektkern. Betrieb und Entwicklung parallel.

**Modulbezug:** CRISP-DM/MLOps, 4 V's, Medallion (K1, K3+K4).
**Datei:** `02_architektur_vorgehen.md`

## 3 — Ingestion & Speicherung (400 W) 🔄 *+~90 W ergänzen*

Bestand: drei Quellen, Batch-statt-Streaming (Kafka/CDC konzeptionell), NDJSON
append-only, DuckDB+Parquet, 718 MB→2,3 MB, 3,1 s Rebuild (Hadoop/Spark konzeptionell),
GitHub Actions als Cloud-Analogie, Sicherheit in einem Satz.
**Zu ergänzen:** konkrete Umsetzung der Erfassung — Retry/Backoff-Politik, Trigger-
Redundanz, Tagesrotation/Partitionierungsschema, Idempotenz des Resolution-Fetchers.

**Datei:** `03_ingestion_speicherung.md`

## 4 — Transformation & Datenmodell (350 W) ⬜ **NEU — Kern der Umsetzung**

- **Grain:** 1 Zeile = Stadt × Zieltag × Temperatur-Bucket; Begründung (jeder Bucket ist
  ein eigener binärer Markt), Alternative verworfen.
- **As-of-Politik (Leakage-Schutz):** Einfrieren auf den letzten Stand vor Mitternacht
  Ortszeit; warum `endDate` als Cut ungeeignet wäre; Audit-Spalte `hours_to_event_end`.
- **Label-Definition und Revision:** Reanalyse vs. offizielle Marktauflösung, Wechsel
  der Quelle, Mismatch als dokumentierte Limitation.
- **Normalisierung:** gemischte Einheiten (NYC °F, 2-Grad-Bänder), Bucket-Parser,
  doppelt kodiertes JSON, „jüngster Abruf gewinnt"-Dedup, datei-übergreifender Join.
- **Idempotenz:** deterministischer Full-Rebuild + eingebaute QS-Abbrüche
  (PK-Eindeutigkeit, genau ein Gewinner je Tag, Normierung, Leakage-Audit).
- **Lineage:** jede Silver-Spalte auf Rohfeld + Regel zurückführbar.

**Modulbezug:** Datenmodellierung/Aufbereitung, Medallion Silver (K3+K4).
**Belege:** `docs/cleaned_schema_AP1.1.md`, `docs/DECISIONS_AP1.1–1.3`, `build_silver.py`,
`docs/lineage.md`. **Datei:** `04_transformation_datenmodell.md`

## 5 — Betriebskonzept: Observability & Fehlertoleranz (450 W) ⬜

Fünf Säulen mit Ist-Implementierung (18 Qualitäts- + 8 Anomalie-Checks,
datengetriebene Schwellwerte). Prepare–Detect–Resolve–Prevent an **drei realen
Vorfällen**: Scheduler-Ausfall → Trigger-Redundanz; Merge-Race → union-merge +
Push-Retry; Fehlalarm → Schweregrad-Trennung. 8/8 Resilienz-Nachweise. Restrisiken.

**Modulbezug:** Observability 5 Säulen (K8), PDRP + Fehlertoleranz (K8+K10).
**Belege:** `docs/betriebskonzept_notizen.md`, `docs/alerting_konzept.md`, beide
Incident-Docs, `scripts/harden/test_resilience.py`. **Datei:** `05_betriebskonzept.md`

## 6 — Ergebnisse, kompakt (130 W) ⬜

**Bewusst knapp** (Prüferhinweis). Nur: Korpusumfang; Aufbau der Evaluation in zwei
Sätzen (zeitliche Validierung mit Embargo, Bewertung auf Tagesverteilungen);
**eine** Kernaussage — der Markt führt, aber wegen Schärfe, nicht wegen besserer
Kalibrierung; die Modellklasse ist nicht der Engpass, sondern die Informationsbasis.
Vergleichstabelle **in den Anhang**, nicht in den Fließtext.

**Belege:** `docs/modell1_logreg_ergebnisse.md`, `docs/modell2_gbm_ergebnisse.md`.
**Datei:** `06_ergebnisse.md`

## 7 — Fazit & Ausblick (120 W → **auf ~160 W erhöht**, s. Hinweis unten) ⬜

Pipeline erfüllt ihren Zweck: belastbarer, auditierbarer, reproduzierbarer Korpus.
Limitierender Faktor ist Datenqualität, nicht Modellierung. Ausblick: Skalierungspfad
(mehr Städte/Leads), Governance/Strategie je Halbsatz gestreift.

**Datei:** `07_fazit.md`

---

## Anhang (zählt nicht zum Wortlimit)

Code-Auszüge (`run_ingestion.py`, `src/raw_store.py`, `build_silver.py` As-of-Logik,
`quality_checks.py`), Schema- und Lineage-Tabelle, Modell-Vergleichstabelle,
Architekturdiagramm aus `docs/lineage.md`.

---

## Budget-Nachsteuerung (Stand AP F4)

Die Abschnitte 2–6 liegen zusammen **151 W unter** ihrem Budget (1.579 statt 1.730).
Damit die Arbeit nicht deutlich unter 2.000 W landet, werden Einleitung und Fazit
entsprechend angehoben: **Einleitung ~200 W** (statt 150), **Fazit ~160 W** (statt 120).
Erwarteter Endstand: **~1.940 W** — innerhalb der üblichen Toleranz von „ca. 2.000",
mit Reserve für Quellenverweise bei der Endredaktion.
