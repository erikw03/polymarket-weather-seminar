# 7 Fazit und Ausblick

> **Rohfassung (AP F5, Freeze-Stand 14.08.).** Budget: ~160 Wörter — Ist siehe Fußzeile.

Die Pipeline erfüllt ihren Zweck: Aus zwei öffentlichen Schnittstellen ist ein
Korpus von [Z: 618] Stadt-Tagen entstanden, der unbeaufsichtigt wächst, nach jedem
Lauf automatisch geprüft wird und dessen Werte sich bis zur einzelnen Rohzeile
zurückverfolgen lassen.

Die zentrale Erkenntnis ist methodischer Natur. Nicht die Modellwahl begrenzt die
Aussagekraft, sondern die Datenqualität: Erst der Vergleich zweier plausibler
Zielgrößen legte offen, dass sie nur in [Z: 32,7 %] der Fälle übereinstimmen – ein
Befund, der die Definition der Zielgröße veränderte und ohne verlustfreie
Rohdatenhaltung nicht korrigierbar gewesen wäre. Die strikte Trennung von Roh- und
abgeleiteten Zonen erwies sich damit nicht als formale Übung, sondern als praktische
Voraussetzung, Entwurfsfehler folgenlos zu revidieren.

Weiterführend wäre der Korpus um zusätzliche Prognosezeitpunkte und
Ensemble-Streuungen erweiterbar; die Architektur skaliert über eine Konfigurationsliste
auf weitere Städte. Fragen der Governance und einer langfristigen Datenstrategie
bleiben bei einem Vorhaben dieser Größe bewusst ausgeklammert.

---
*Wortzahl: 141 Fließtext (Budget 160). Belege: `docs/freeze/KENNZAHLEN.md`,
`docs/DECISIONS_AP1.2.md`, `docs/lineage.md`.*
