# 2 Vorgehen und Architektur

> **Rohfassung (AP 4.2, Stand 30.07.).** Zahlen mit `[Z: …]` werden beim Data Freeze
> (AP 4.4) zentral aktualisiert. Budget: 400 Wörter — Ist siehe Fußzeile.

Als Prozessrahmen dient CRISP-DM, allerdings nicht als lineare Abfolge, sondern
ausdrücklich iterativ: Zwei Rückkopplungen vom *Data Understanding* zurück in die
Datenaufbereitung prägen das Projekt. Erstens zeigte die systematische Sichtung des
Rohkorpus, dass die Marktpreise am Zieltag faktisch zum Ergebnis werden — der
Yes-Preis des späteren Gewinners stieg an einem Beispieltag von 0,40 (09:01 UTC) auf
1,00 (19:01 UTC). Daraus folgte die zentrale Schemaentscheidung, sämtliche Merkmale
auf den letzten Stand vor Mitternacht Ortszeit des Zieltags einzufrieren; andernfalls
hätte das Modell bereits realisierte Temperatur als Vorhersage verwendet. Zweitens
ergab die spätere Quantifizierung, dass das ursprünglich gewählte Label aus der
Wetter-Reanalyse nur in [Z: 23 %] der Fälle exakt mit dem offiziellen Marktergebnis
übereinstimmt, mit einem systematischen Versatz von bis zu [Z: +2 °C] in München.
Diese Erkenntnis führte zum Wechsel der Label-Quelle — ein Eingriff, der ohne
verlustfreie Rohdatenhaltung nicht mehr möglich gewesen wäre.

Genau deshalb folgt die Speicherarchitektur dem Medallion-Ansatz. Die Bronze-Zone
hält alle API-Antworten unverändert und ausschließlich anfügend (write once, read
many); sie umfasst derzeit [Z: 718 MB in 104 Tagesdateien aus 42 Sammeltagen].
Die Silver-Zone destilliert daraus [Z: 6.227] bereinigte, typisierte Zeilen
([Z: 575] Stadt-Tage), die Gold-Zone die daraus abgeleitete Merkmalstabelle für die
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

---
*Wortzahl: 356 Fließtext (Budget 400; ~44 W Reserve für Überarbeitung/Quellenverweise).
Belege: `docs/architektur_notizen.md`,
`docs/raw_inspection_report_AP1.1.md`, `docs/DECISIONS_AP1.1–1.3`, `docs/DECISIONS_AP1.2.md` (D3-Revision).*
