# 6 Ergebnisse

> **Rohfassung (AP F4, Freeze-Stand 14.08.).** Bewusst knapp gehalten — der Schwerpunkt
> der Arbeit liegt auf Aufbau und Betrieb der Pipeline. Vergleichstabelle im Anhang.
> Budget: 130 Wörter — Ist siehe Fußzeile.

Der erzeugte Korpus umfasst [Z: 618] Stadt-Tage im Zeitraum [Z: März bis August 2026].
Bewertet wird nicht die einzelne Zeile, sondern die je Stadt und Zieltag normierte
Wahrscheinlichkeitsverteilung über alle Temperatur-Buckets; validiert wird zeitlich
fortschreitend mit einer Sperrfrist von zwei Tagen, da amtliche Ergebnisse verzögert
eintreffen.

Beide Modelle übertreffen die naive Prognoseregel deutlich, bleiben aber hinter dem
Markt zurück ([Z: Brier 0,79 gegenüber 0,66]). Bemerkenswert ist der Grund: Die
Wahrscheinlichkeiten sind nahezu gleich gut kalibriert; der Markt trifft lediglich
häufiger das richtige Intervall ([Z: 47,5 % gegenüber 33 %]). Der Vorsprung beruht
somit auf zusätzlicher Information, nicht auf besserer Wahrscheinlichkeitsschätzung.
Dazu passt, dass das komplexere Verfahren die interpretierbare Basislösung nicht
schlägt – begrenzend wirkt die Informationsbasis, nicht die Modellklasse.

---
*Wortzahl: 116 Fließtext (Budget 130). Belege: `docs/freeze/KENNZAHLEN.md`,
`docs/modell1_logreg_ergebnisse.md`, `docs/modell2_gbm_ergebnisse.md`.*
