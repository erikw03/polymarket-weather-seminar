# Entscheidungs- & Änderungslog — AP 4.3 (Schreiben Ingestion + Speicherung)

> Plan: Abschnitte zu Ingestion, Medallion, Storage-Entscheidungen (mit 4-V-Begründung).
> Meilenstein: ~800 Wörter gesamt.

## Design-Entscheidungen

- **U1 Kennzahlen vor dem Schreiben gemessen, nicht aus dem Gedächtnis zitiert:**
  Abrufe/Stadt/Tag (aktuell 33–38, Median 35 — der frühere Wert 28–35 stammt aus der
  Zeit vor dem zweiten Trigger), Zonengrößen und Rebuild-Laufzeit wurden für diesen
  Abschnitt frisch erhoben. Belegt im Zahlenblock unten.
- **U2 Zwei gemessene Größen tragen die Storage-Argumentation:**
  (a) **718 MB Bronze → 2,3 MB Silver** (Faktor ~300) macht den Medallion-Zweck
  anschaulich: Bronze ist Archiv, nicht Arbeitsmenge. (b) **3,1 s Full-Rebuild**
  begründet zugleich den Verzicht auf verteilte Verarbeitung *und* die Wahl
  „vollständig neu bauen statt inkrementell laden". Beide Zahlen ersetzen mehrere
  Sätze Prosa — wichtig bei 350 Wörtern Budget.
- **U3 Konzeptionelle Modulthemen bewusst als Einzelsätze**, nicht als Absätze:
  Kafka/CDC, Hadoop/Spark und Cloud/S3+Lambda werden jeweils dort verankert, wo die
  eigene Entscheidung fällt, und mit einer Zahl begründet. Das erfüllt das
  Kapitel-Mapping („nur konzeptionell mit Begründung der Vereinfachung"), ohne das
  knappe Budget zu sprengen.
- **U4 Sicherheit (K9) als ein Satz** am Abschnittsende: keylose öffentliche APIs,
  keine personenbezogenen Daten, einziges Geheimnis ist das Repo-scoped Token des
  externen Cron-Triggers. Mehr wäre für dieses Projekt Zeremonie.
- **U5 Budgetkontrolle wie in AP 4.2**: Wortzahl maschinell gemessen (Zähler ignoriert
  Header/Blockquote/Fußzeile); bei Überschreitung wird gekürzt statt das Budget
  stillschweigend zu dehnen.

## Zahlenstand bei Erstellung (30.07.)

| Größe | Wert | Erhebung |
|---|---|---|
| Abrufe je Stadt/Tag | 33–38 (Median 35) | 7 volle Tage, `polymarket_*.ndjson` |
| Bronze | 718 MB, 104 Tagesdateien, 42 Sammeltage | `du -sh data/raw` |
| Silver | 2,3 MB DuckDB + 624 KB Parquet; 6.227 Zeilen | `build_silver.py` |
| Gold | 1,3 MB DuckDB; 6.048 Zeilen | `build_features.py` |
| Full-Rebuild Bronze→Silver | **3,1 s** | `/usr/bin/time -p build_silver.py` |

## Arbeitsschritte-Protokoll

| # | Schritt | Ergebnis |
|---|---|---|
| 1 | Kennzahlen gemessen (U1) | s. Tabelle |
| 2 | Log angelegt | diese Datei |
| 3 | Abschnitt 3 geschrieben | `docs/arbeit/03_ingestion_speicherung.md`, **309 W** (Budget 350) |
| 4 | Wortzahl geprüft | Abschnitt 2: 358 W · Abschnitt 3: 309 W · **Gesamt 667 W** |

## Meilenstein — mit ehrlicher Einordnung

✅ **Abschnitt „Ingestion & Speicherung" geschrieben**, inkl. 4-V-Begründung der
Storage-Entscheidungen und aller drei nur-konzeptionellen Modulthemen.

⚠️ **Gesamtstand 667 W statt der im Plan genannten ~800 W.** Das ist **kein Rückstand**,
sondern Budgettreue: Die verbindliche Gliederung sieht für die Abschnitte 2+3
zusammen 750 W vor; 667 W bedeuten 83 W bewusste Reserve. Beim wissenschaftlichen
Überarbeiten kommen erfahrungsgemäß Wörter hinzu (Quellenverweise, Präzisierungen),
nicht weg. Text künstlich auf 800 W aufzublähen wäre bei einem 2.000-Wörter-Limit
kontraproduktiv — die verbleibenden Abschnitte (4: 450 W Betriebskonzept, 5: 400 W
Analyse) tragen den meisten Modulstoff und brauchen ihr Budget vollständig.

## Übergabe

- **AP 4.4 (So 03.08.) — DATA FREEZE**, kritischer Meilenstein: finaler `git pull`,
  `build_silver` + `build_features`, beide Analyse-Skripte auf dem Freeze-Stand;
  danach **alle `[Z: …]`-Marker in `docs/arbeit/` in einem Durchgang** gegen die
  Freeze-Artefakte aktualisieren. Zu entscheiden ist dort, ob die Ergebnis-JSONs
  ausnahmsweise committet werden (Freeze-Referenz trotz `data/processed`-Ignore).
- **AP 5.1** schreibt Abschnitt 4 (450 W) aus `docs/betriebskonzept_notizen.md`
  und den drei Incident-Docs.
