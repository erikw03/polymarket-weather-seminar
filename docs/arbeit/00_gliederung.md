# Detail-Gliederung der Seminararbeit (AP 4.2)

**Thema:** Datenpipeline & -korpus aus Wetterprognose- und Prognosemarktdaten
**Umfang:** 2.000 Wörter netto (~7–9 Seiten) + Code als Anhang (zählt nicht mit)
**Abgabe:** 16.08.2026 · **Data Freeze:** 03.08.2026

Legende Status: ✍️ geschrieben · ⬜ offen · Wortangaben = verbindliches Budget (U2).

| # | Abschnitt | Budget | Status | AP |
|---|---|---|---|---|
| 1 | Einleitung & Use-Case | 200 | ⬜ | 5.3 |
| 2 | Vorgehen & Architektur | 400 | ✍️ | **4.2** |
| 3 | Ingestion & Speicherung | 350 | ⬜ | 4.3 |
| 4 | Betriebskonzept: Observability & Fehlertoleranz | 450 | ⬜ | 5.1 |
| 5 | Analyse: Modelle vs. Markt | 400 | ⬜ | 5.2 |
| 6 | Fazit & Ausblick | 200 | ⬜ | 5.3 |
| | **Summe** | **2.000** | | |

---

## 1 — Einleitung & Use-Case (200 W, AP 5.3)

**Inhalt:** Prognosemärkte als Informationsaggregatoren; Forschungsfrage: *Wie gut
tracken Polymarkets implizite Wahrscheinlichkeiten für Tages-Höchsttemperaturen die
Wetterprognose und das tatsächliche Ergebnis?* Abgrenzung: rein analytisch, read-only,
kein Handel (in DE ohnehin geoblockt). Zielgröße: Verteilung über ~11 Temperatur-Buckets
je Stadt und Tag; Bewertung mit Brier/Log Loss/Accuracy.

**Modulbezug:** CRISP-DM *Business Understanding* (K1).
**Belege:** `README.md`, `docs/cleaned_schema_AP1.1.md` (§Zweck).

## 2 — Vorgehen & Architektur (400 W, **AP 4.2 — geschrieben**)

**Inhalt:** CRISP-DM als Prozessrahmen mit zwei belegten Iterationsschleifen
(Data-Understanding → Schemaänderung; Label-Revision D3). Medallion-Architektur
Bronze→Silver→Gold, lokal/kostenfrei umgesetzt. Die 4 V's als Begründung der
Architekturentscheidungen — insbesondere *Veracity* als eigentlicher Projektkern.
Parallelität von Betrieb und Entwicklung (MLOps-Gedanke): Ingestion lief ab Tag 1
produktiv, während Schema und Analyse entstanden.

**Modulbezug:** CRISP-DM/MLOps (K1), 4 V's (K1), Medallion (K3+K4).
**Belege:** `docs/architektur_notizen.md`, `docs/DECISIONS_AP1.1–1.3`,
`docs/raw_inspection_report_AP1.1.md`.
**Datei:** `02_architektur_vorgehen.md`

## 3 — Ingestion & Speicherung (350 W, AP 4.3)

**Inhalt:** Drei Quellen (Open-Meteo Forecast/Archiv, Polymarket Gamma+CLOB,
Resolution-Fetcher). Stündliches Batch-Polling statt Streaming — mit Begründung
(Märkte resolven täglich; Sub-Minuten-Latenz ohne Erkenntnisgewinn) → hier
**Kafka/CDC nur konzeptionell** einordnen (jede NDJSON-Zeile ≙ Event).
Speicherformate: NDJSON append-only (Bronze), DuckDB + Parquet (Silver/Gold),
Partitionierung nach `city`; Volumenbegründung → **Hadoop/Spark nur konzeptionell**.
Cloud-Betrieb über GitHub Actions + Git-Repo als Datenarchiv → **S3/Lambda-Analogie**.
Kernentscheidung As-of-Cut (D-1 23:59 lokal) als Leakage-Schutz kurz anreißen.

**Modulbezug:** Rohformat/Parquet (K3+K4), Kafka/CDC (K3, konzeptionell),
Hadoop/Spark (K4, konzeptionell), Cloud (K6, konzeptionell).
**Belege:** `docs/lineage.md`, `docs/cleaned_schema_AP1.1.md`, `src/raw_store.py`,
`.github/workflows/ingest.yml`.
**Zahlen:** [Z: 718 MB Raw, 104 Tagesdateien, 42 Sammeltage, 28–35 Abrufe/Stadt/Tag].

## 4 — Betriebskonzept: Observability & Fehlertoleranz (450 W, AP 5.1)

**Inhalt:** Fünf Säulen mit Ist-Implementierung (Freshness/Volume/Schema/Nulls/Lineage)
= 18 automatisierte Checks + 8 Anomalie-Checks; datengetriebene statt geratener
Schwellwerte. Prepare–Detect–Resolve–Prevent an **drei realen Vorfällen**:
(a) Scheduler-Ausfall 21.06. → Trigger-Redundanz; (b) Merge-Race 21.07. → union-merge
+ Push-Retry; (c) Fehlalarm 30.07. → Schweregrad-Trennung im Check. Belegte
Fehlertoleranz: 8/8 Resilienz-Nachweise (Retry-Politik, Quellen-Isolation, Idempotenz).
Lineage bis Datei+Zeile demonstrierbar. Ehrliche Restrisiken.

**Modulbezug:** Observability 5 Säulen (K8), PDRP + Fehlertoleranz (K8+K10).
**Belege:** `docs/betriebskonzept_notizen.md`, `docs/alerting_konzept.md`,
`docs/incident_2026-07-21_*.md`, `docs/incident_2026-07-30_*.md`,
`scripts/harden/test_resilience.py`, `quality_checks.py`, `anomaly_checks.py`.

## 5 — Analyse: Modelle vs. Markt (400 W, AP 5.2)

**Inhalt:** Analysis-Zone (Feature-Tabelle, Grain = Stadt × Tag × Bucket), zeitliche
Validierung mit Embargo (Resolution-Latenz!), Bewertung auf Tages-Verteilungen.
Zwei Modelle (LogReg, Gradient Boosting) gegen zwei Baselines (Markt, naive
Forecast-Regel). **Kernbefund:** Markt führt (Brier [Z: 0,653] vs. [Z: 0,777/0,782]),
aber *nicht* wegen besserer Kalibrierung (ECE nahezu gleich, GBM+isotonic sogar
minimal besser) — sondern wegen **Schärfe**. Modell lernt den Station-über-Forecast-Bias
selbstständig. GBM schlägt LogReg nicht → Engpass ist Information, nicht Modellklasse.

**Modulbezug:** CRISP-DM *Modeling/Evaluation* (K1).
**Belege:** `docs/modell1_logreg_ergebnisse.md`, `docs/modell2_gbm_ergebnisse.md`,
`model_framework.py`, JSON-Artefakte in `data/processed/analysis/`.

## 6 — Fazit & Ausblick (200 W, AP 5.3)

**Inhalt:** Pipeline erfüllt ihren Zweck (belastbarer, auditierbarer Korpus);
Datenqualität ist der limitierende Faktor, nicht die Modellierung. Größte Limitation:
Quellen-Mismatch Open-Meteo↔Wunderground ([Z: 23 % exakte Übereinstimmung,
München-Bias +2 °C]) — gelöst durch Wechsel der Label-Quelle. Ausblick: mehr Leads,
Ensemble-Spreads, stündliche Profile; Skalierungspfad zu mehr Städten.

**Modulbezug:** Reflexion/Governance (K11, gestreift).
**Belege:** `docs/DECISIONS_AP1.2.md` (D3-Revision), `docs/modell2_gbm_ergebnisse.md` (§Fazit).

---

## Nicht behandelt (bewusst, mit Kurzbegründung im Text)

- **Sicherheit (K9):** öffentliche, keylose APIs, keine personenbezogenen Daten →
  ein Satz in Abschnitt 3 (einziges Geheimnis: PAT des externen Cron-Triggers).
- **Governance breit (K11) / Strategie (K12):** für ein Ein-Personen-Forschungsprojekt
  ohne Stakeholder-Struktur nicht sinnvoll skalierbar → je ein Halbsatz im Fazit.

## Anhang (zählt nicht zum Wortlimit)

Code-Auszüge: `run_ingestion.py`, `src/raw_store.py`, `build_silver.py` (As-of-Logik),
`quality_checks.py`, `model_framework.py`; Schema-Tabelle + Lineage-Tabelle aus
`docs/cleaned_schema_AP1.1.md`; Vergleichstabelle der Modelle.
