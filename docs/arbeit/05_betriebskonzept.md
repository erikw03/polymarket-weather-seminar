# 5 Betriebskonzept: Observability und Fehlertoleranz

> **Rohfassung (AP F3, Freeze-Stand 14.08.).** Zahlen aus `docs/freeze/KENNZAHLEN.md`.
> Budget: 450 Wörter — Ist siehe Fußzeile.

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

---
*Wortzahl: 383 Fließtext (Budget 450; ~67 W Reserve). Belege:
`docs/betriebskonzept_notizen.md`, `docs/alerting_konzept.md`,
`docs/incident_2026-07-21_gate-fail.md`, `docs/incident_2026-07-30_gate-fail.md`,
`quality_checks.py`, `anomaly_checks.py`, `scripts/harden/test_resilience.py`.*
