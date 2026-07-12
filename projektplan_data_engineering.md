# Projektplan — Data Engineering Seminararbeit
**Thema:** Datenpipeline & -korpus aus Wetterprognose- und Prognosemarktdaten
**Abgabe:** Sa, 16.08.2026 · **Data Freeze:** So, 03.08.2026 · **Heute:** Mi, 08.07.2026

---

## ⚡ PLAN-ANPASSUNG (Stand So, 13.07.) — Projekt läuft ~5 Tage VOR Plan

**Ist-Stand:** Woche 1 komplett (AP 1.1–1.4 ✅) UND Woche 2 fast komplett (AP 2.1–2.3 ✅)
bereits am 13.07. erledigt. Offen aus Woche 2: nur AP 2.4 (Konsolidierung, leicht).

**Angepasste Termine (Meilensteine bleiben, Puffer wächst):**
- AP 2.4 → Mo/Di 14.–15.07. (statt 19./20.07.)
- Woche 3 (Features & Modell-Gerüst, AP 3.1–3.4) → start ~Di 15.07. (statt 22.07.)
- Woche 4 (Modell 2 + Schreibbeginn) → ~ab 22.07. → **Schreibstart ~1 Woche früher**
  (adressiert Risiko #1 „Schreiben" direkt)
- **Data Freeze bleibt 03.08.** (jeder zusätzliche Sammeltag vergrößert den Korpus;
  finale Modell-Läufe wie geplant auf Freeze-Daten)
- Gewonnene Zeit = zusätzlicher Puffer vor Rohfassung (10.08.) und Abgabe (16.08.)

---

---

## Eckdaten & Regeln

- **Umfang Arbeit:** ca. 2.000 Wörter netto (~7–9 Seiten) + Code als **Anhang** (zählt nicht mit)
- **Arbeitsabende:** Di, Do, Fr, Sa, So — ~3h/Abend (2–4h)
- **Prinzip:** Ingestion läuft die ganze Zeit weiter (cron). Alles andere passiert parallel.
- **Schreiben ist dein #1-Risiko** → beginnt bewusst früh (ab Woche 4), nicht am Ende.
- **Modelle:** (1) Logistic Regression (interpretierbare Baseline), (2) Gradient Boosting (XGBoost/LightGBM). Architektur unterstützt weitere. Fokus: saubere Zeitreihen-Validierung, ehrliche Baselines, kalibrierte Wahrscheinlichkeiten (Brier/Log Loss).

## Architektur-Leitbild (Medallion, lokal)

```
RAW (Bronze)        CLEANED (Silver)         ANALYSIS (Gold)
timestamped JSON  →  DuckDB + Parquet      →  Feature-Tabelle  →  Modelle
append-only/WORM     (join Wetter×Markt)      (ML-ready)          + Vergleich
        │                    │                     │
        └──── Observability-Modul (Freshness, Volume, Schema, Nulls, Lineage) ────┘
                     Betrieb: Retry/Backoff · Idempotenz · Backfill · Alerting-Konzept
```

**Kapitel-Mapping (was in die Arbeit kommt):**
- Tragend: CRISP-DM/MLOps (K1) · 4 V's (K1) · Medallion/Rohformat/Parquet (K3+K4) · Observability 5 Säulen (K8) · Prepare-Detect-Resolve-Prevent + Fehlertoleranz (K8+K10)
- Nur konzeptionell (mit Begründung der Vereinfachung): Kafka/CDC (K3) · Hadoop/Spark (K4) · Cloud/S3+Lambda (K6)
- Weglassen/streifen: Sicherheit (K9) · Governance breit (K11) · Strategie (K12)

---

## Wochenübersicht

| Woche | Zeitraum | Fokus | Ergebnis am Wochenende |
|---|---|---|---|
| 1 | 08.–13.07. | Cleaning & Korpus | Raw→Cleaned Pipeline + Backfill läuft |
| 2 | 14.–20.07. | Observability & Betrieb | Qualitätsmodul + gehärtete Pipeline |
| 3 | 21.–27.07. | Features & Modell-Gerüst | Analysis-Zone + Modell-Framework |
| 4 | 28.07.–03.08. | **DATA FREEZE** + Modelle + Schreiben-Start | Beide Modelle fertig, Ergebnisse stehen |
| 5 | 04.–10.08. | Schreiben Hauptteil | Rohfassung komplett |
| 6 | 11.–16.08. | Feinschliff & Abgabe | Fertige Arbeit + Code-Anhang |

---

## Arbeitspakete pro Abend

### WOCHE 1 — Cleaning & Korpus (08.–13.07.)

**AP 1.1 — Do 10.07. (3h): Raw sichten & Cleaned-Schema entwerfen**
- Mit Claude: bestehende Raw-JSONs inspizieren, Zielschema definieren (1 Zeile = 1 Markt × 1 Tag)
- Entscheiden: welche Felder aus Wetter (forecast max/min, observed) + Markt (Preis, Resolution, Volumen)
- ✅ Meilenstein: dokumentiertes Cleaned-Schema

**AP 1.2 — Fr 11.07. (3h): Transform Raw→Cleaned bauen**
- Mit Claude: Python-Transform, join Wetter×Markt, Schreiben nach DuckDB + Parquet
- Idempotent, wiederholbar
- ✅ Meilenstein: erste Cleaned-Tabelle existiert

**AP 1.3 — Sa 12.07. (3–4h): Backfill historische Daten**
- Mit Claude: Open-Meteo Historical Forecast + Archive rückwirkend ziehen, in Raw einspeisen
- Cleaned-Transform darauf laufen lassen → Korpus wächst rückwirkend
- ✅ Meilenstein: Korpus deckt auch Zeit vor Sammelstart ab

**AP 1.4 — So 13.07. (2h, leicht): Puffer & Doku**
- Lücken schließen, kurze Architektur-Notizen für später
- ✅ Woche-1-Abschluss: Cleaned-Pipeline steht

### WOCHE 2 — Observability & Betrieb (14.–20.07.)

**AP 2.1 — Di 15.07. (3h): Datenqualitäts-Modul (5 Säulen)**
- Mit Claude: Checks für Freshness (Zeit seit letzter Lieferung), Volume (erwartete Zeilenzahl), Schema, Null-Rate
- ✅ Meilenstein: `quality_checks.py` läuft über den Korpus

**AP 2.2 — Do 17.07. (3h): Anomalie-Erkennung & Alerting-Konzept**
- Mit Claude: einfache Schwellwert-Checks + Log-Ausgabe; Alerting nur konzeptionell beschreiben
- ✅ Meilenstein: Checks melden Auffälligkeiten

**AP 2.3 — Fr 18.07. (3h): Pipeline härten (Fehlertoleranz)**
- Mit Claude: Retry/Backoff prüfen, Idempotenz testen, bewusst Fehler simulieren (API down)
- ✅ Meilenstein: Pipeline überlebt Ausfälle sauber

**AP 2.4 — Sa/So 19.–20.07. (je 2–3h): Lineage-Doku + Betriebskonzept-Notizen**
- Data Lineage dokumentieren (welches Feld kommt woher), Betriebskonzept-Bausteine sammeln
- ✅ Woche-2-Abschluss: Betrieb steht, Material für Arbeit gesammelt

### WOCHE 3 — Features & Modell-Gerüst (21.–27.07.)

**AP 3.1 — Di 22.07. (3h): Analysis-Zone & Feature-Engineering**
- Mit Claude: Features bauen (Forecast-Werte, Differenzen, Vortageswerte, Saisonalität), ML-ready Tabelle
- ✅ Meilenstein: Feature-Tabelle existiert

**AP 3.2 — Do 24.07. (3–4h): Modell-Framework (mehrere Modelle)**
- Mit Claude: Framework mit TimeSeriesSplit, sauberer Train/Test-Trennung, Metriken (Brier, Log Loss, Accuracy)
- Baselines definieren: Marktpreis-als-Prädiktor + naive Forecast-Regel
- ✅ Meilenstein: Framework trainiert Platzhalter-Modell fehlerfrei

**AP 3.3 — Fr 25.07. (3h): Modell 1 — Logistic Regression sauber**
- Mit Claude: LogReg trainieren, Koeffizienten interpretieren, gegen Baselines vergleichen
- ✅ Meilenstein: Modell 1 mit Ergebnissen

**AP 3.4 — Sa/So 26.–27.07. (je 3h): Puffer + erste Ergebnis-Sichtung**
- Reserve für Überläufe; erste Interpretation "Modell vs. Markt"
- ✅ Woche-3-Abschluss: Modell-Pipeline + erstes Modell fertig

### WOCHE 4 — Freeze, Modell 2 & Schreiben startet (28.07.–03.08.)

**AP 4.1 — Di 29.07. (3–4h): Modell 2 — Gradient Boosting sauber**
- Mit Claude: XGBoost/LightGBM, Kalibrierung, Feature-Importance, Vergleich mit Modell 1 + Baselines
- ✅ Meilenstein: beide Modelle + Vergleichstabelle

**AP 4.2 — Do 31.07. (3h): Gliederung + Schreiben Methodik/Architektur**
- Mit Claude: Detail-Gliederung der 2.000 Wörter, erster Abschnitt (Architektur/Vorgehen)
- ✅ Meilenstein: Gliederung steht, ~400 Wörter geschrieben

**AP 4.3 — Fr 01.08. (3h): Schreiben Ingestion + Speicherung**
- Mit Claude: Abschnitte zu Ingestion, Medallion, Storage-Entscheidungen (mit 4-V-Begründung)
- ✅ Meilenstein: ~800 Wörter gesamt

**AP 4.4 — So 03.08. — 🧊 DATA FREEZE (3–4h)**
- Ingestion final laufen lassen, Korpus einfrieren, finale Modell-Läufe auf Freeze-Daten
- Mit Claude: finale Ergebnistabelle fixieren
- ✅ **Kritischer Meilenstein: Daten & Ergebnisse final, ab jetzt nur noch Schreiben**

### WOCHE 5 — Schreiben Hauptteil (04.–10.08.)

**AP 5.1 — Di 05.08. (3h):** Betriebskonzept-Kapitel (Observability, Fehlertoleranz, Prepare-Detect-Resolve-Prevent) → ~1.200 W
**AP 5.2 — Do 07.08. (3h):** Analyse/Ergebnis-Kapitel (Modelle, Vergleich, Interpretation) → ~1.600 W
**AP 5.3 — Fr 08.08. (3h):** Einleitung, Use-Case, Fazit/Ausblick → ~2.000 W (Rohfassung komplett)
**AP 5.4 — Sa/So 09.–10.08. (je 2–3h):** Code-Anhang aufbereiten, Kürzen auf 2.000 netto, erste Selbst-Korrektur
- ✅ **Woche-5-Abschluss: vollständige Rohfassung + Code-Anhang**

### WOCHE 6 — Feinschliff & Abgabe (11.–16.08.)

**AP 6.1 — Di 12.08. (3h):** Inhaltlicher Feinschliff mit Claude (Argumentation, Begründungen, Konsistenz)
**AP 6.2 — Do 14.08. (3h):** Sprache, Zitation, Formatierung, Wortzahl final
**AP 6.3 — Fr 15.08. (2h):** Letzter Durchgang, PDF-Export, Anhang prüfen
**AP 6.4 — Sa 16.08.:** 📤 **ABGABE** (nicht bis zur letzten Minute — Vormittag)
- ✅ Puffer eingebaut: 4 Tage Reserve zwischen Rohfassung (10.08.) und Abgabe (16.08.)

---

## Risiken & Gegenmaßnahmen

| Risiko (dein Ranking) | Gegenmaßnahme im Plan |
|---|---|
| #1 Schreiben | Beginnt Woche 4, nicht am Ende. Claude hilft bei Struktur + Formulierung. 4 Tage Puffer. |
| #2 Technik | Pipeline in Wochen 1–3 fertig, bevor Schreibdruck kommt. Jeder Abend ein klarer Meilenstein. |
| #3 Zeit | Data Freeze 03.08. trennt "Bauen" von "Schreiben". Leichte So-Abende als Puffer. |
| #4 Bewertung | Kapitel-Mapping stellt sicher, dass Modulinhalte sichtbar adressiert werden. |

## Fixe Meilensteine (nicht verschieben!)
- **So 13.07.** — Cleaned-Pipeline steht
- **So 20.07.** — Betrieb/Observability steht
- **So 03.08.** — 🧊 DATA FREEZE + beide Modelle fertig
- **So 10.08.** — Rohfassung komplett
- **Sa 16.08.** — 📤 Abgabe
