# Vorfall 2026-07-21 — roter CI-Lauf (Quality-Gate FAIL)

> Realer Betriebsvorfall; dokumentiert als Prepare-Detect-Resolve-Prevent-Beispiel
> fürs Betriebskonzept-Kapitel. Kein Datenverlust im Repo.

## Detect
Workflow-Lauf `29828356201` (workflow_dispatch, 12:00 UTC) rot. Fehlgeschlagener
Schritt: **Quality gate** — `X1 Raw-Schema weather 3/147` und `X2 Raw-Schema
polymarket 3/75` Verstöße; alle 16 anderen Checks grün. Das Gate hat also genau
das getan, wofür es gebaut wurde: eine Schema-Anomalie sichtbar gemacht (roter
Lauf = P1-Mail-Pfad).

## Diagnose
- Committete Daten **sauber**: `weather_2026-07-21.ndjson` wächst monoton +8/h
  (…120→128→136), 0 Konfliktmarker, 0 Schema-Verstöße im Repo.
- Der Check sah aber **147/75** Zeilen — mehr als die 136/68 im finalen Commit.
  Eine append-only Datei verliert keine Zeilen ⇒ die 147 stammten aus einem
  transient inkonsistenten **Arbeitsbaum**, nicht aus committeten Daten.
- Verräterisch: in der Git-Historie fehlt der Commit des `11:59`-Schedule-Laufs
  (der `12:01`-Commit hängt direkt am `11:03`-Commit).

## Root Cause
GitHubs `schedule` (nominell `:17`) feuerte wegen Scheduler-Verzögerung erst
`:59` und kollidierte mit dem pünktlichen cron-job.org-Dispatch (`:00`). Beide
Läufe hängten an dieselbe Tagesdatei an → Rebase-Konflikt am Dateiende. Der
Workflow hatte `git pull --rebase --autostash … || true`: das **`|| true`
verschluckte den Konflikt** und ließ Konfliktmarker (`<<<<<<< / ======= />>>>>>>`,
= genau 3 Nicht-JSON-Zeilen je Datei) im Arbeitsbaum. `build_silver` +
Quality-Gate lasen diesen Baum → 3+3 „Schema-Verstöße" → rot. Der Schedule-Lauf
verlor dabei seine Snapshot-Runde (vom Cron-Lauf überschrieben).

## Resolve / Prevent (Fix vom 21.07.)
1. **`.gitattributes`: `*.ndjson merge=union`** — konkurrierende Anhänge werden
   konfliktfrei zusammengeführt (Zeilen **beider** Läufe bleiben erhalten, keine
   Marker, kein Snapshot-Verlust). Lokal in isoliertem Git-Test verifiziert.
2. **Push-Schritt gehärtet:** `|| true` entfernt; stattdessen Retry-Schleife
   (fetch → rebase → push, bei Fehlschlag `rebase --abort` + erneuter Versuch,
   nach 5 Fehlversuchen echter Exit 1). Ein kaputter Baum kann nicht mehr
   unbemerkt in Build/Gate durchrutschen.

## Bewertung
- **Datenintegrität:** unversehrt (committeter Korpus lückenlos).
- **Schweregrad:** niedrig — ein Fehlalarm + eine verlorene Snapshot-Runde
  (für die betroffene Stunde blieb der Cron-Snapshot erhalten; stündliche
  Sampling-Kadenz unverändert erfüllt).
- **Nutzen:** Der Vorfall belegt die Observability-Kette (Detect→Resolve→Prevent)
  an einem echten Fall — und die Redundanz zweier Trigger ist nach dem Fix
  gefahrlos (union-merge macht Kollisionen harmlos statt schädlich).
