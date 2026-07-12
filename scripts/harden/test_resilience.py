"""
AP 2.3 — Fehlertoleranz-Nachweise (reproduzierbar, ohne Seiteneffekte).

Simulationen laufen gegen httpx.MockTransport bzw. Temp-Verzeichnisse —
das echte Raw wird NIE beruehrt (U1). Exit 0 = alle Nachweise bestanden.

Nachweise:
  T1  Retry bei transienten Fehlern (2x HTTP 500 -> 200 nach 3 Versuchen)
  T2  KEIN Retry bei 404 (Client-Fehler wird sofort durchgereicht)
  T3  Persistenter Netzausfall -> Abbruch nach 5 Versuchen mit Original-Exception
  T4  Retry bei HTTP 429 (Rate-Limit)
  T5  Quellen-Isolation: Wetter-Crash stoppt Polymarket/Resolutions nicht (Exit 0)
  T6  Totalausfall beider Quellen -> Exit 1 (Alarm-Pfad)
  T7  Korrupte NDJSON-Zeile: Transform ueberspringt + zaehlt (kein Crash)
  T8  Idempotenz Transform: 2 Laeufe -> identische Zeilenzahl + Checksumme (ohne Lauf-Metadaten)

Aufruf:  python scripts/harden/test_resilience.py
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
import tempfile

import httpx
import tenacity

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from src import http_client  # noqa: E402

PASSED = []


def check(name: str, ok: bool, detail: str = "") -> None:
    PASSED.append(ok)
    print(f"  [{'OK' if ok else 'FEHLGESCHLAGEN'}] {name}" + (f" - {detail}" if detail else ""))


def with_mock(handler):
    """Ersetzt den HTTP-Client durch einen MockTransport (kein echtes Netz)."""
    http_client._client = httpx.Client(transport=httpx.MockTransport(handler))


def no_wait():
    """Retry-Wartezeiten fuer Tests auf 0 setzen (Verhalten bleibt identisch)."""
    http_client.get_json.retry.wait = tenacity.wait_fixed(0)


def main() -> int:
    print("== T1-T4: Retry/Backoff-Politik (MockTransport) ==")
    no_wait()

    calls = {"n": 0}
    def h500_then_ok(req):
        calls["n"] += 1
        return httpx.Response(500 if calls["n"] <= 2 else 200, json={"ok": True})
    with_mock(h500_then_ok)
    r = http_client.get_json("https://mock/x")
    check("T1 transient 500x2 -> Erfolg", r == {"ok": True} and calls["n"] == 3,
          f"{calls['n']} Versuche")

    calls["n"] = 0
    def h404(req):
        calls["n"] += 1
        return httpx.Response(404)
    with_mock(h404)
    try:
        http_client.get_json("https://mock/x")
        check("T2 404 ohne Retry", False)
    except httpx.HTTPStatusError:
        check("T2 404 ohne Retry", calls["n"] == 1, f"{calls['n']} Versuch")

    calls["n"] = 0
    def hdown(req):
        calls["n"] += 1
        raise httpx.ConnectError("API down (simuliert)")
    with_mock(hdown)
    try:
        http_client.get_json("https://mock/x")
        check("T3 persistenter Ausfall", False)
    except httpx.ConnectError:
        check("T3 persistenter Ausfall -> 5 Versuche, Original-Exception", calls["n"] == 5,
              f"{calls['n']} Versuche")

    calls["n"] = 0
    def h429_then_ok(req):
        calls["n"] += 1
        return httpx.Response(429 if calls["n"] == 1 else 200, json={"ok": 1})
    with_mock(h429_then_ok)
    r = http_client.get_json("https://mock/x")
    check("T4 429 wird retried", calls["n"] == 2, f"{calls['n']} Versuche")

    print("== T5/T6: Quellen-Isolation in run_ingestion (Orchestrierung) ==")
    import run_ingestion
    from src import ingest_polymarket, ingest_resolutions, ingest_weather

    orig = (ingest_weather.run, ingest_polymarket.run, ingest_resolutions.run)
    def boom():
        raise RuntimeError("Quelle down (simuliert)")
    ingest_weather.run = boom
    ingest_polymarket.run = lambda: ["fake_file"]      # liefert erfolgreich
    ingest_resolutions.run = lambda: 0
    rc = run_ingestion.main()
    check("T5 Wetter-Crash isoliert (Exit 0, Polymarket lief)", rc == 0, f"Exit={rc}")

    ingest_polymarket.run = boom                        # jetzt beide down
    rc = run_ingestion.main()
    check("T6 Totalausfall -> Exit 1 (Alarm)", rc == 1, f"Exit={rc}")
    ingest_weather.run, ingest_polymarket.run, ingest_resolutions.run = orig

    print("== T7: korrupte NDJSON-Zeile (Temp-Kopie, echtes Raw unberuehrt) ==")
    import build_silver
    with tempfile.TemporaryDirectory() as tmp:
        p = os.path.join(tmp, "t.ndjson")
        good = json.dumps({"_meta": {"city": "X"}, "v": 1})
        with open(p, "w") as fh:
            fh.write(good + "\n" + "{KAPUTT###\n" + good + "\n")
        build_silver._lines_total = build_silver._lines_corrupt = 0
        recs = list(build_silver.iter_ndjson(p))
        check("T7 korrupte Zeile uebersprungen + gezaehlt",
              len(recs) == 2 and build_silver._lines_corrupt == 1,
              f"{len(recs)} Records, {build_silver._lines_corrupt} korrupt")

    print("== T8: Idempotenz des Transforms (2 Laeufe, Checksumme ohne Metadaten) ==")
    import subprocess
    import duckdb
    def checksum():
        con = duckdb.connect(os.path.join(ROOT, "data/processed/silver.duckdb"), read_only=True)
        n, cs = con.execute("""
            SELECT COUNT(*),
                   SUM(hash(city || target_date || bucket_label || yes_price_raw ||
                            COALESCE(market_resolved_bucket, '-') ||
                            COALESCE(CAST(forecast_max_native AS VARCHAR), '-')))
            FROM market_bucket_daily""").fetchone()
        con.close()
        return n, cs
    py = os.path.join(ROOT, ".venv", "bin", "python")
    subprocess.run([py, os.path.join(ROOT, "build_silver.py")], capture_output=True, check=True)
    a = checksum()
    subprocess.run([py, os.path.join(ROOT, "build_silver.py")], capture_output=True, check=True)
    b = checksum()
    check("T8 identisch (Zeilen + Checksumme)", a == b, f"{a[0]} Zeilen, hash gleich: {a == b}")

    print("-" * 60)
    ok = all(PASSED)
    print(f"Ergebnis: {sum(PASSED)}/{len(PASSED)} Nachweise bestanden")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
