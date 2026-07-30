# Vorfall 2026-07-30 — 7 rote CI-Läufe in Folge (Fehlalarm des Quality-Gates)

> Realer Betriebsvorfall. **Kein Datenverlust, kein Pipeline-Fehler** — ein zu
> streng entworfener Check. Dokumentiert als Beispiel für die Alarm-Design-Frage
> „was ist FAIL, was ist WARN?" (Betriebskonzept-Kapitel).

## Detect
Ab 2026-07-30 **04:00 UTC** schlugen alle Workflow-Läufe fehl (7 in Folge, je eine
rote Mail); bis 03:27 UTC war alles grün. Fehlgeschlagener Schritt: **ausschließlich**
`Quality gate`. Ingestion, Daten-Commit und `build_silver` waren in **jedem** Lauf
erfolgreich. Meldung: `X2 Raw-Schema polymarket 1/52 Verstöße`.

## Diagnose
- Betroffen: `polymarket_2026-07-30.ndjson`, **Zeile 26**, abgerufen **04:03:17 UTC**
  (exakt der Beginn der Fehlerserie).
- Inhalt: der frisch gelistete London-Markt für den 1. August
  (`highest-temperature-in-london-on-august-1-2026`) kam mit **allen 11 Buckets ohne
  das Feld `outcomePrices`** von der Gamma-API.
- **Transient:** derselbe Markt hatte im Snapshot **05:03 vollständige Preise**
  (0 fehlende Felder) — und in allen späteren Snapshots ebenso.
- **Selten:** in 14 Tagen genau **1 betroffene Zeile von ~1.800**.
- `build_silver.py` behandelt den Fall bereits korrekt
  (`except (KeyError, ValueError, json.JSONDecodeError): continue`, Zeilen 373–376
  und 219–224) → Bucket wird sauber übersprungen. Daher war der Build grün.

## Root Cause
Zwei Eigenschaften wirkten zusammen:
1. **Gamma listet Märkte ~D+2 im Voraus, bevor Preise existieren** — ein legitimer,
   kurzlebiger API-Zustand, kein Defekt.
2. Der X2-Check wertete **jede** Abweichung als `FAIL` und prüft die **gesamte**
   jüngste Tagesdatei. Da die Raw-Zone **append-only** ist, bleibt die Zeile von
   04:03 dauerhaft in der Datei — der Check fand sie stündlich erneut.

Folge: Der Check war strenger als die Pipeline selbst und blockierte den Rest des
Tages, obwohl die Daten seit 05:03 wieder einwandfrei waren. Ohne Eingriff hätte
sich der Fehler erst um 00:00 UTC (neue Tagesdatei) von selbst „geheilt".

**Abgrenzung:** anderer Fehler als am 21.07. (dort Merge-Konfliktmarker durch
Trigger-Race, 3+3 Verstöße). Jener Fix (union-merge + Push-Retry) wirkt weiterhin.

## Resolve / Prevent (Fix vom 30.07.)
X2-Check in `quality_checks.py` trennt jetzt nach **Schweregrad**:

| Kategorie | Beispiele | Status |
|---|---|---|
| **hart** | kaputtes JSON, fehlende Top-Level-Keys, Event ohne Datum | **FAIL** |
| **weich** | einzelner Markt ohne/mit unparsebarem `outcomePrices`/`clobTokenIds`, leeres `groupItemTitle` | **WARN** |
| **weich, aber massenhaft** | > `SOFT_VIOLATION_MAX_RATE` (5 %) der Zeilen | **FAIL** (echter API-Ausfall) |

Ausgabe zeigt beide Zahlen (`0 hart / 1 weich von 52`), damit im Log sofort
erkennbar ist, worum es geht. Rohdaten und Transform blieben unangetastet.

### Verifikation (alle bestanden)
| Test | Erwartung | Ergebnis |
|---|---|---|
| Echter Fehlerfall (Datei vom 30.07.) | WARN, Exit 0 | ✓ `0 hart / 1 weich von 52` |
| Kaputtes JSON angehängt | FAIL | ✓ `1 hart / 1 weich` |
| Top-Level-Key entfernt | FAIL | ✓ `1 hart / 1 weich` |
| `outcomePrices` in 20 % der Zeilen entfernt | FAIL (Schwelle) | ✓ `0 hart / 11 weich` |
| Echte Rohdaten nach den Tests | unverändert | ✓ (Tests nur gegen Kopien) |

## Bewertung
- **Datenintegrität:** unversehrt; der betroffene Markt ist seit 05:03 vollständig erfasst.
- **Schweregrad:** niedrig — reiner Fehlalarm, aber mit 7 unnötigen Alarmmails genau
  das Muster, vor dem `docs/alerting_konzept.md` warnt (Alarm-Müdigkeit).
- **Lerneffekt fürs Kapitel:** Ein Qualitäts-Check darf nicht strenger sein als die
  Verarbeitung, die er absichert. Entscheidend ist die Frage „ist das Datenprodukt
  unbrauchbar?" — nicht „weicht irgendetwas ab?". Die Schweregrad-Trennung plus
  Raten-Schwelle ist dieselbe Logik wie `CORRUPT_MAX_RATE` im Transform (AP 2.3/U3)
  und wird damit zum durchgängigen Entwurfsmuster des Projekts.
