# Entscheidungs- & Änderungslog — AP 1.4 (Puffer & Doku, Woche-1-Abschluss)

> Leichtes AP laut Plan (So 13.07.): Lücken schließen, Architektur-Notizen. Vorgaben unverändert.

## Gesundheits-Check (Ausgangspunkt)

- Ingestion: beide Trigger grün (schedule + workflow_dispatch, stündlich), Raw aktuell bis 12./13.07.
- Offene offizielle Labels nur für 12.07. (LON/MUC/NYC) = **normale Resolution-Latenz 1–2 Tage**,
  kein Handlungsbedarf (stündlicher Fetcher fängt sie automatisch; Tokio 12.07. bereits da).
- Kein weiterer Daten-Handlungsbedarf: Lücke 17.–19.06. wurde bereits in AP 1.3 geschlossen.

## Geschlossene Lücken (dieses AP)

1. **Repo-Hygiene:** `.DS_Store`, `*.Rhistory` in `.gitignore` (OS-/Editor-Artefakte lagen untracked herum).
2. **Workflow-Deprecation:** `actions/checkout` v4→v5, `actions/setup-python` v5→v6
   (Node-20-Warnung in jedem Lauf); Verifikation per manuellem Actions-Lauf.
3. **NICHT „geschlossen", bewusst:** NYC 18.06. (1 dünn gehandelter Backfill-Tag, U3-Regel) —
   datengetriebener Ausschluss, wird als Limitation geführt, nicht künstlich aufgefüllt.

## Deliverable

- `docs/architektur_notizen.md` — Schreibvorlage für die Arbeit entlang des Kapitel-Mappings
  (CRISP-DM, 4 V's, Medallion, Observability-5-Säulen, PDRP/Fehlertoleranz, Konzept-Kapitel),
  jede Zahl mit Beleg-Verweis ins Repo.

## Woche-1-Meilenstein

✅ **„Cleaned-Pipeline steht" (Plan: So 13.07.) erreicht.** Bestand: 3 autonome Quellen,
freigegebenes Silver-Schema inkl. D3-Revision, idempotenter Transform mit QS-Checks,
Backfill integriert → 5 457 Zeilen / 505 City-Days (01.03.–13.07.). Übergabe Woche 2
(AP 2.1 Datenqualitäts-Modul): offene Checks siehe `DECISIONS_AP1.3.md` §Offene Punkte.
