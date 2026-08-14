# 3 Ingestion und Speicherung

> **Rohfassung (AP 4.3, Stand 30.07.).** Zahlen mit `[Z: …]` werden beim Data Freeze
> (AP 4.4) zentral aktualisiert. Budget: 350 Wörter — Ist siehe Fußzeile.

Erfasst werden drei öffentliche, schlüsselfreie Quellen: Wetterprognosen und
Reanalyse-Messwerte von Open-Meteo, Marktdaten von Polymarket sowie – als eigene
dritte Quelle – die offiziellen Marktauflösungen. Letztere sind notwendig, weil
aufgelöste Märkte aus der laufenden Abfrage verschwinden; ein täglicher, idempotenter
Nachfasslauf sichert das amtliche Ergebnis, bevor es verloren geht. Die Erfassung
läuft stündlich und erreicht 39 bis 45 Abrufe je Stadt und Tag.

Bewusst wird periodisches Batch-Polling statt eines Streaming-Ansatzes eingesetzt.
Die Märkte lösen einmal täglich auf, die zugrunde liegenden Wettermodelle
aktualisieren im Stundenbereich; eine ereignisgetriebene Architektur mit
Sekundenlatenz (Kafka, CDC) würde erheblichen Betriebsaufwand erzeugen, ohne die
Fragestellung zu verbessern. Konzeptionell bleibt die Nähe erhalten: Jede Zeile der
Rohdateien ist ein unveränderliches Ereignis mit Zeitstempel und entspricht damit
einem Datensatz in einem Kafka-Topic.

Ein Lauf verarbeitet die drei Quellen nacheinander und gegeneinander abgeschottet:
Fällt eine aus, laufen die übrigen zu Ende. Jede Antwort wird unverändert in eine
schlanke Hülle gelegt, die Quelle, Stadt, Abrufzeitpunkt, Wetterstation und
Maßeinheit festhält – diese Angaben tragen später sowohl die Deduplizierung als auch
den Herkunftsnachweis. Vorübergehende Fehler wie Zeitüberschreitungen oder
Serverfehler werden mit wachsenden Wartezeiten wiederholt, dauerhafte Fehler dagegen
sofort durchgereicht. Der Nachfasslauf für Marktauflösungen prüft zunächst den
Bestand und fragt nur Ereignisse ab, für die noch kein Ergebnis vorliegt; er ist
dadurch beliebig oft wiederholbar.

Die Bronze-Zone speichert diese Ereignisse als tagesrotierende NDJSON-Dateien, rein
anfügend und unverändert. Zeilenweises Anfügen ist absturzsicher, benötigt keine
Sperren bei parallelen Läufen und bleibt versionierbar. Die Tagesrotation dient
zugleich als Partitionierung: Ein Kalendertag entspricht genau einer Datei je Quelle. Silver und Gold liegen
dagegen in DuckDB, ergänzt um nach Stadt partitionierte Parquet-Dateien als
portables Austauschformat. Der Kontrast begründet die Architektur: rund 1 Gigabyte
Rohdaten destillieren zu 3 Megabyte geprüfter Silver-Daten. Bronze ist Archiv,
nicht Arbeitsmenge.

Aus derselben Größenordnung folgen zwei weitere Entscheidungen. Der vollständige
Neuaufbau beider abgeleiteten Zonen dauert 4,2 Sekunden auf einem einzelnen
Rechenkern. Verteilte Verarbeitung (Hadoop, Spark) wäre daher reiner Overhead; sie
würde erst bei Datenmengen jenseits des Arbeitsspeichers oder bei mehreren hundert
Städten lohnen. Und weil der Neuaufbau so günstig ist, wird bewusst vollständig statt
inkrementell geladen – die einfachste korrekte Form von Idempotenz.

Der Betrieb erfolgt kostenfrei in der Cloud über GitHub Actions, wobei das
Git-Repository selbst als versioniertes Datenarchiv dient. Die Rollen entsprechen
einer klassischen Cloud-Architektur: der Zeitplan-Auslöser einem Scheduling-Dienst,
der Runner einer Funktionsausführung, das Repository einem versionierten
Objektspeicher. Sicherheitsanforderungen sind gering, da ausschließlich öffentliche,
schlüsselfreie Schnittstellen ohne personenbezogene Daten gelesen werden; einziges
Geheimnis ist das eng begrenzte Zugriffstoken des externen Auslösers.

---
*Wortzahl: 403 Fließtext (Budget 400 — punktgenau, +3 W Toleranz).
Belege: `docs/lineage.md`
(Quellen-Register, Datenfluss), `src/raw_store.py`, `src/ingest_resolutions.py`,
`.github/workflows/ingest.yml`, `docs/betriebskonzept_notizen.md` §K1.*
