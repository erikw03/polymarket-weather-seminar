# Entscheidungs- & Änderungslog — AP 4.2 (Gliederung + Schreiben Methodik/Architektur)

> Plan: Detail-Gliederung der 2.000 Wörter, erster Abschnitt (Architektur/Vorgehen).
> Meilenstein: Gliederung steht, ~400 Wörter geschrieben.

## Design-Entscheidungen

- **U1 Eigener Ordner `docs/arbeit/`** für Textbausteine, getrennt von den Notizen
  (`architektur_notizen.md`, `betriebskonzept_notizen.md` bleiben Materialsammlung).
  Ein Abschnitt = eine Datei, nummeriert nach Gliederung → am Ende einfach zusammensetzbar,
  und jeder Abschnitt bleibt einzeln überarbeitbar.
- **U2 Wortbudget verbindlich je Abschnitt**, Summe exakt 2.000 (netto, ohne Anhang).
  Begründung: 2.000 Wörter sind für den Stoffumfang knapp; ohne Budget läuft der
  Architektur-Teil über und das Ergebnis-Kapitel wird zu dünn. Budget wird pro AP
  gegen den Ist-Stand geprüft (Wortzähler im Log).
- **U3 Gliederung folgt dem Kapitel-Mapping des Projektplans**, nicht der
  Projekt-Chronologie: tragende Modulinhalte (CRISP-DM/4 V's, Medallion, Observability
  5 Säulen, PDRP/Fehlertoleranz) bekommen eigene Abschnitte; nur-konzeptionelle Themen
  (Kafka/CDC, Hadoop/Spark, Cloud) werden als **begründete Vereinfachungen** in die
  jeweils passenden Abschnitte eingebettet statt in ein eigenes „Was wir nicht taten".
- **U4 Jede Zahl im Text hat einen Repo-Beleg** (Skript/Doc), in der Gliederung als
  Quellenspalte hinterlegt. Verhindert beim Schreiben unter Zeitdruck Zahlendreher
  und macht die Arbeit prüfbar.
- **U5 Zahlenstand = Data Freeze (03.08.).** Alle jetzt geschriebenen Zahlen sind
  Platzhalter mit Stand 30.07. und werden in AP 4.4 **einmal zentral** gegen die
  Freeze-Artefakte aktualisiert. Im Text sind sie deshalb als `[Z: …]` markiert,
  damit sie beim Freeze-Durchgang auffindbar sind.
- **U6 Eigenleistungs-Hinweis:** Die Textentwürfe sind Rohfassungen zur Überarbeitung
  durch den Verfasser, keine abgabefertige Prosa. Fachliche Aussagen sind aus den
  eigenen Projektartefakten belegt; Formulierung/Argumentation müssen vom Verfasser
  geprüft und verantwortet werden (Prüfungsordnung/Eigenständigkeitserklärung).

## Zahlenstand bei Erstellung (30.07.)

| Größe | Wert | Quelle |
|---|---|---|
| Raw | 718 MB, 104 Tagesdateien, 42 Sammeltage | `data/raw/` |
| Silver | 6.227 Zeilen, 575 City-Days (01.03.–30.07.) | `build_silver.py` |
| Gold | 6.048 Zeilen, 558 City-Days | `build_features.py` |
| Modelle | Markt 0,653 · LogReg 0,777 · GBM+iso 0,782 · naiv 1,289 (Brier) | AP 3.3/4.1-Artefakte |

## Arbeitsschritte-Protokoll

| # | Schritt | Ergebnis |
|---|---|---|
| 1 | Datenkette aktualisiert, Kennzahlen erhoben | s. Tabelle oben |
| 2 | Log angelegt | diese Datei |
| 3 | Detail-Gliederung | `docs/arbeit/00_gliederung.md` (6 Abschnitte, Budget 2.000 W) |
| 4 | Abschnitt 2 geschrieben | `docs/arbeit/02_architektur_vorgehen.md`, **356 W Fließtext** (Budget 400) |
| 5 | Wortzahl maschinell geprüft | Zähler ignoriert Header/Blockquote/Fußzeile → 356 |

## Meilenstein

✅ **Gliederung steht, ~400 Wörter geschrieben.** Sechs Abschnitte mit verbindlichem
Budget (Summe exakt 2.000), je mit Modulbezug, Repo-Belegen und AP-Zuordnung; der
Architektur-/Vorgehens-Abschnitt ist als Rohfassung geschrieben.

## Übergabe an AP 4.3 (Schreiben Ingestion + Speicherung)

- Ziel: Abschnitt 3 (350 W) → Gesamtstand dann ~750 W (Plan nennt ~800 W).
- Dort unterzubringen: die drei nur-konzeptionellen Modulthemen (Kafka/CDC,
  Hadoop/Spark, Cloud/S3+Lambda) **als begründete Vereinfachungen** (U3) sowie der
  Ein-Satz-Hinweis zu Sicherheit (K9).
- Material liegt vollständig in `docs/lineage.md` (Quellen-Register, Datenfluss) und
  `docs/betriebskonzept_notizen.md` §K1.
