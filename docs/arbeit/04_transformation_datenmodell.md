# 4 Transformation und Datenmodell

> **Rohfassung (AP F2, Freeze-Stand 14.08.).** Zahlen aus `docs/freeze/KENNZAHLEN.md`.
> Budget: 350 Wörter — Ist siehe Fußzeile.

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

---
*Wortzahl: 330 Fließtext (Budget 350). **Redaktionshinweis:** As-of-Regel und
Label-Wechsel werden in Abschnitt 2 als CRISP-DM-Iteration eingeführt, hier als
Umsetzungsregel vertieft — beim Endlesen auf unnötige Wortwiederholung prüfen.
Belege: `docs/cleaned_schema_AP1.1.md`
(Schema + Lineage-Tabelle), `docs/DECISIONS_AP1.1–1.3`, `build_silver.py`,
`docs/freeze/KENNZAHLEN.md`.*
