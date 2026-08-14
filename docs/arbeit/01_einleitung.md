# 1 Einleitung und Anwendungsfall

> **Rohfassung (AP F5, Freeze-Stand 14.08.).** Budget: ~200 Wörter — Ist siehe Fußzeile.

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

---
*Wortzahl: 174 Fließtext (Budget 200). Belege: `README.md`,
`docs/cleaned_schema_AP1.1.md`, `docs/lineage.md`.*
