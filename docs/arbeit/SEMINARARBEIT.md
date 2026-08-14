# Aufbau und Betrieb einer Datenpipeline für Wetterprognose- und Prognosemarktdaten

*Seminararbeit Data Engineering · Erik Wegner · August 2026*

*Datenstand (Data Freeze): 14.08.2026 · Code und ergänzende Artefakte im Anhang*

---

## 1 Einleitung und Anwendungsfall

Prognosemärkte gelten als wirksame Aggregatoren verstreuter Information: Teilnehmende
handeln Kontrakte auf künftige Ereignisse, wodurch Preise als Wahrscheinlichkeiten
lesbar werden. Besonders geeignet für eine Überprüfung sind Wettermärkte, denn hier
existiert mit der numerischen Wettervorhersage eine unabhängige, öffentlich
verfügbare Vergleichsprognose sowie ein eindeutiges, kurzfristig eintretendes
Ergebnis. Daraus ergibt sich die Fragestellung, wie gut die marktimpliziten
Wahrscheinlichkeiten für die Tages-Höchsttemperatur einer Stadt die meteorologische
Prognose und das tatsächliche Ergebnis abbilden.

Der eigentliche Aufwand liegt dabei nicht in der Auswertung, sondern in der
Datengrundlage: Ein solcher Datensatz existiert nicht. Marktpreise sind flüchtig,
werden nicht historisiert und verschwinden nach der Auflösung eines Marktes aus der
Schnittstelle; sie lassen sich nachträglich nicht rekonstruieren. Wer die Frage
beantworten will, muss die Daten zunächst laufend, verlustfrei und nachvollziehbar
selbst erheben.

Gegenstand dieser Arbeit ist daher der Entwurf, die Umsetzung und der Betrieb einer
Datenpipeline, die aus zwei öffentlichen Schnittstellen einen belastbaren,
auditierbaren und reproduzierbaren Korpus erzeugt. Die anschließende Modellierung
dient als Nachweis der Verwendbarkeit und wird bewusst knapp gehalten. Sämtliche
Zugriffe erfolgen ausschließlich lesend auf öffentliche Daten; es findet keinerlei
Handel statt.

## 2 Vorgehen und Architektur

Als Prozessrahmen dient CRISP-DM, allerdings nicht als lineare Abfolge, sondern
ausdrücklich iterativ: Zwei Rückkopplungen vom *Data Understanding* zurück in die
Datenaufbereitung prägen das Projekt. Erstens zeigte die systematische Sichtung des
Rohkorpus, dass die Marktpreise am Zieltag faktisch zum Ergebnis werden — der
Yes-Preis des späteren Gewinners stieg an einem Beispieltag von 0,40 (09:01 UTC) auf
1,00 (19:01 UTC). Daraus folgte die zentrale Schemaentscheidung, sämtliche Merkmale
auf den letzten Stand vor Mitternacht Ortszeit des Zieltags einzufrieren; andernfalls
hätte das Modell bereits realisierte Temperatur als Vorhersage verwendet. Zweitens
ergab die spätere Quantifizierung, dass das ursprünglich gewählte Label aus der
Wetter-Reanalyse nur in 32,7 % der Fälle exakt mit dem offiziellen Marktergebnis
übereinstimmt, mit einem systematischen Versatz von bis zu +1,4 °C in München.
Diese Erkenntnis führte zum Wechsel der Label-Quelle — ein Eingriff, der ohne
verlustfreie Rohdatenhaltung nicht mehr möglich gewesen wäre.

Genau deshalb folgt die Speicherarchitektur dem Medallion-Ansatz. Die Bronze-Zone
hält alle API-Antworten unverändert und ausschließlich anfügend (write once, read
many); sie umfasst derzeit rund 1 Gigabyte in 149 Tagesdateien aus 57 Sammeltagen.
Die Silver-Zone destilliert daraus 6.887 bereinigte, typisierte Zeilen
(635 Stadt-Tage), die Gold-Zone die daraus abgeleitete Merkmalstabelle für die
Modellierung. Entscheidend ist die Rückrichtung: Beide abgeleiteten Zonen werden bei
jedem Lauf vollständig und deterministisch neu erzeugt. Die beiden oben genannten
Korrekturen erforderten daher lediglich einen erneuten Transformationslauf und keine
einzige neue API-Abfrage — Idempotenz ist hier kein Selbstzweck, sondern die
praktische Voraussetzung dafür, Entwurfsfehler folgenlos zu revidieren.

Die Dimensionierung der Architektur orientiert sich an den 4 V's. *Volume* ist mit
weniger als einem Gigabyte bewusst klein, was den Verzicht auf verteilte Verarbeitung
rechtfertigt; *Velocity* ist durch täglich auflösende Märkte begrenzt, weshalb
stündliches Batch-Polling genügt; *Variety* verlangt Normalisierung zweier
API-Familien mit verschachtelten JSON-Feldern und gemischten Einheiten. Der
eigentliche Projektkern ist jedoch *Veracity*: Die oben beschriebenen
Datenqualitätsbefunde sind keine Randnotizen, sondern bestimmen Label-Definition,
Schema und Aussagekraft der Analyse.

Methodisch getrennt davon läuft der Betrieb: Die Erfassung arbeitete vom ersten Tag
an produktiv weiter, während Schema, Transformation und Analyse entstanden. Diese
Parallelität von laufendem Betrieb und Weiterentwicklung entspricht dem
MLOps-Grundgedanken und war hier nicht optional — Marktpreise sind flüchtig und
lassen sich nachträglich nicht rekonstruieren.

## 3 Ingestion und Speicherung

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

## 4 Transformation und Datenmodell

Die Silver-Zone verdichtet die Rohereignisse zu einer Tabelle mit klar definierter
Granularität: Eine Zeile beschreibt einen Temperatur-Bucket einer Stadt an einem
Zieltag. Diese Wahl folgt der Struktur der Quelle, denn auf Polymarket ist jeder
Bucket technisch ein eigener binärer Markt mit eigener Kennung und eigenem
Orderbuch. Eine gröbere Modellierung auf Ereignisebene wurde verworfen, weil Anzahl
und Zuschnitt der Buckets zwischen Städten variieren und ein starres Spaltenschema
daran zerbrechen würde. Insgesamt entstehen 6.887 Zeilen für 635 Stadt-Tage.

Die wichtigste Regel der Transformation ist zeitlicher Natur. Von den rund 41
Abrufen je Stadt und Tag geht genau einer in die Merkmale ein: der letzte vor
Mitternacht Ortszeit des Zieltags. Damit liegt das Tagesmaximum zum Bewertungs­
zeitpunkt vollständig in der Zukunft. Das nominelle Marktende um 12:00 UTC wäre als
Schnitt ungeeignet, da es lokal je nach Stadt bereits Nachmittag oder Abend ist. Wie
weit jede Zeile vom Marktende entfernt ist, wird als eigene Spalte mitgeführt und
maschinell geprüft; der geringste Vorlauf im Korpus beträgt 8,0 Stunden.

Als Zielgröße dient das amtliche Marktergebnis. Die zunächst verwendete
Reanalyse-Messung wird weiterhin als Vergleichsgröße geführt: Beide Quellen stimmen
nur in 32,7 % der Fälle exakt überein, mit einem systematischen Versatz von
+1,4 °C in München. Dieser Quellenunterschied ist als Limitation dokumentiert
und war der Grund für den Wechsel der Zielgröße.

Erheblichen Anteil hat die Vereinheitlichung heterogener Rohdaten. Preise und
Kennungen liegen als doppelt kodierte JSON-Zeichenketten vor; Bucket-Bezeichnungen
folgen vier Mustern, darunter offene Ränder und – ausschließlich für New York –
Fahrenheit-Bänder mit zwei Grad Breite. Temperaturen werden zusätzlich nach Celsius
normalisiert, während die Originaleinheit erhalten bleibt. Beobachtete Messwerte
erscheinen erst in späteren Tagesdateien, was einen dateiübergreifenden Verbund
erfordert; bei mehrfach gelieferten Werten gewinnt stets der jüngste Abruf.

Die gesamte Zone wird bei jedem Lauf deterministisch neu aufgebaut. Vier Prüfungen
brechen den Lauf bei Verletzung ab, darunter Schlüsseleindeutigkeit, genau ein
Gewinner je Zieltag und die Prüfung des zeitlichen Vorlaufs. Jede Spalte ist über eine
dokumentierte Regel auf ihr Rohfeld zurückführbar.

## 5 Betriebskonzept: Observability und Fehlertoleranz

Da die Erfassung unbeaufsichtigt läuft und Marktpreise nicht rückwirkend beschafft
werden können, ist die Überwachung kein Zusatz, sondern Teil der Pipeline. Umgesetzt
sind die fünf Säulen der Datenqualität in 18 automatisierten Prüfungen, die nach
jedem Lauf ausgeführt werden. Sie decken Aktualität (Alter des jüngsten Abrufs je
Quelle), Menge (Zeilen je Tagesdatei gegen ein erwartetes Band), Schema
(Pflichtfelder, Dekodierbarkeit verschachtelter Felder, Abgleich der Silver-Spalten
gegen das freigegebene Schema), Nullwerte und Verteilungen (Labelabdeckung,
Preissummen, Schlüsseleindeutigkeit, Prüfung des zeitlichen Vorlaufs) sowie
Herkunftsnachweis ab. Ergänzend prüfen acht weitere Regeln die inhaltliche
Plausibilität, etwa auffällige Prognosefehler oder Ergebnisse, die der Markt zuvor
nahezu ausgeschlossen hatte.

Bewusst wurden die Schwellwerte nicht geschätzt, sondern aus dem laufenden Betrieb
gemessen. Da sich die Städte deutlich unterscheiden, berechnen die
Plausibilitätsprüfungen ihre Grenzen zur Laufzeit je Stadt aus robusten Quantilen;
absolute Grenzen fangen zusätzlich echte Datenkorruption ab. Die Prüfungen sind über
einen Rückgabewert an die Ausführungsumgebung gekoppelt: Schlägt eine harte Prüfung
fehl, wird der Lauf als fehlerhaft markiert und der Betreiber automatisch
benachrichtigt. Bewusst erfolgt diese Prüfung erst **nach** dem Sichern der Rohdaten,
damit ein Qualitätsalarm niemals die Speicherung gültiger Daten verhindert.

Wie belastbar dieses Konzept ist, zeigen drei tatsächlich aufgetretene Störungen,
die jeweils nach dem Muster Vorbeugen–Erkennen–Beheben–Verhindern bearbeitet wurden.
Zunächst lieferte der Zeitplan-Dienst des Cloud-Anbieters über Stunden keine Läufe;
als Konsequenz wurde ein zweiter, unabhängiger Auslöser ergänzt. Diese Redundanz
verursachte später selbst einen Fehler, weil zwei gleichzeitige Läufe an dieselbe
Tagesdatei anfügten und ein Zusammenführungskonflikt unbemerkt blieb; gelöst wurde
dies durch eine Merge-Strategie, die beide Ergänzungen erhält, sowie einen
Wiederholungsmechanismus beim Schreiben. Der dritte Fall war ein Fehlalarm: Ein
frisch gelisteter Markt ohne Preise ließ die Schemaprüfung sieben Läufe in Folge
fehlschlagen, obwohl die Verarbeitung solche Fälle korrekt überspringt. Daraus
entstand die Regel, zwischen strukturellen Defekten und bekannten, vorübergehenden
Zuständen zu unterscheiden – eine Prüfung darf nicht strenger sein als die
Verarbeitung, die sie absichert.

Die Fehlertoleranz selbst ist nicht behauptet, sondern in acht reproduzierbaren
Nachweisen abgesichert. Sie belegen unter anderem, dass nur vorübergehende Fehler
wiederholt werden, dauerhafte Ausfälle begrenzt abbrechen, der Ausfall einer Quelle
die übrigen nicht beeinträchtigt, einzelne beschädigte Zeilen übersprungen statt
eskaliert werden und zwei aufeinanderfolgende Transformationsläufe identische
Ergebnisse liefern.

Offen bleiben bewusst akzeptierte Restrisiken: Der Zeitplan-Dienst arbeitet ohne
Zusicherung, die Erfassung hängt vollständig an einem Cloud-Anbieter, und amtliche
Marktergebnisse treffen mit ein bis zwei Tagen Verzögerung ein.

## 6 Ergebnisse

Der erzeugte Korpus umfasst 618 Stadt-Tage im Zeitraum März bis August 2026.
Bewertet wird nicht die einzelne Zeile, sondern die je Stadt und Zieltag normierte
Wahrscheinlichkeitsverteilung über alle Temperatur-Buckets; validiert wird zeitlich
fortschreitend mit einer Sperrfrist von zwei Tagen, da amtliche Ergebnisse verzögert
eintreffen.

Beide Modelle übertreffen die naive Prognoseregel deutlich, bleiben aber hinter dem
Markt zurück (Brier 0,79 gegenüber 0,66). Bemerkenswert ist der Grund: Die
Wahrscheinlichkeiten sind nahezu gleich gut kalibriert; der Markt trifft lediglich
häufiger das richtige Intervall (47,5 % gegenüber 33 %). Der Vorsprung beruht
somit auf zusätzlicher Information, nicht auf besserer Wahrscheinlichkeitsschätzung.
Dazu passt, dass das komplexere Verfahren die interpretierbare Basislösung nicht
schlägt – begrenzend wirkt die Informationsbasis, nicht die Modellklasse.

## 7 Fazit und Ausblick

Die Pipeline erfüllt ihren Zweck: Aus zwei öffentlichen Schnittstellen ist ein
Korpus von 618 Stadt-Tagen entstanden, der unbeaufsichtigt wächst, nach jedem
Lauf automatisch geprüft wird und dessen Werte sich bis zur einzelnen Rohzeile
zurückverfolgen lassen.

Die zentrale Erkenntnis ist methodischer Natur. Nicht die Modellwahl begrenzt die
Aussagekraft, sondern die Datenqualität: Erst der Vergleich zweier plausibler
Zielgrößen legte offen, dass sie nur in 32,7 % der Fälle übereinstimmen – ein
Befund, der die Definition der Zielgröße veränderte und ohne verlustfreie
Rohdatenhaltung nicht korrigierbar gewesen wäre. Die strikte Trennung von Roh- und
abgeleiteten Zonen erwies sich damit nicht als formale Übung, sondern als praktische
Voraussetzung, Entwurfsfehler folgenlos zu revidieren.

Weiterführend wäre der Korpus um zusätzliche Prognosezeitpunkte und
Ensemble-Streuungen erweiterbar; die Architektur skaliert über eine Konfigurationsliste
auf weitere Städte. Fragen der Governance und einer langfristigen Datenstrategie
bleiben bei einem Vorhaben dieser Größe bewusst ausgeklammert.
