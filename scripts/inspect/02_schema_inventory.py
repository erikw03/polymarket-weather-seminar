"""AP1.1 Phase A — Inspektionsskript 2: Schema-Inventar (READ-ONLY).

Ermittelt je Quelle die vollständige Feldliste (inkl. verschachtelter Ebenen),
Typen und Präsenz (immer / optional), plus 1 Beispielwert. Für Polymarket wird
auf Event- und Market(Bucket)-Ebene inventarisiert; `clob_quotes` strukturell.
Nur Standardbibliothek, deterministisch, verändert nichts.

Aufruf:  python scripts/inspect/02_schema_inventory.py
"""
from __future__ import annotations

import glob
import json
import os
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class Inv:
    """Sammelt je Feldpfad: Typen, Vorkommen, ein Beispiel."""

    def __init__(self):
        self.types = defaultdict(set)
        self.count = defaultdict(int)
        self.example = {}
        self.total = 0

    def add(self, obj: dict, prefix=""):
        for k, v in obj.items():
            p = f"{prefix}{k}"
            self.count[p] += 1
            self.types[p].add(type(v).__name__)
            if p not in self.example and v not in (None, "", [], {}):
                s = json.dumps(v, ensure_ascii=False)
                self.example[p] = s[:70] + ("…" if len(s) > 70 else "")
            if isinstance(v, dict):
                self.add(v, p + ".")

    def report(self, title: str):
        print(f"\n--- {title} (n={self.total}) ---")
        print(f"{'Feldpfad':46}{'Typ(en)':18}{'Präsenz':>9}  Beispiel")
        for p in sorted(self.count):
            pres = self.count[p] / self.total if self.total else 0
            flag = "immer" if pres >= 0.999 else f"{pres:.1%}"
            print(f"{p:46}{'/'.join(sorted(self.types[p])):18}{flag:>9}  {self.example.get(p, '')}")


def main() -> None:
    # ---------------- Wetter ----------------
    w_by_kind = defaultdict(Inv)
    for f in sorted(glob.glob(os.path.join(ROOT, "data/raw/weather/weather_*.ndjson"))):
        with open(f, encoding="utf-8") as fh:
            for line in fh:
                rec = json.loads(line)
                kind = rec["_meta"].get("kind")
                inv = w_by_kind[kind]
                inv.total += 1
                inv.add(rec)
    print("=" * 72)
    print("WETTER — Feldinventar je kind")
    for kind, inv in sorted(w_by_kind.items()):
        inv.report(f"kind = {kind}")

    # ---------------- Polymarket ----------------
    line_inv = Inv()          # Top-Level + _meta
    ev_inv = Inv()            # Event-Ebene (gamma_events[i])
    mk_inv = Inv()            # Market/Bucket-Ebene (…markets[j]) — ohne Event-Rekursion
    cq_inv = Inv()            # clob_quotes[token_id]-Ebene
    for f in sorted(glob.glob(os.path.join(ROOT, "data/raw/polymarket/polymarket_*.ndjson"))):
        with open(f, encoding="utf-8") as fh:
            for line in fh:
                rec = json.loads(line)
                line_inv.total += 1
                line_inv.add({"_meta": rec["_meta"]})
                for ev in rec.get("gamma_events", []):
                    ev_inv.total += 1
                    ev_inv.add({k: v for k, v in ev.items() if k != "markets"})
                    for mk in ev.get("markets", []):
                        mk_inv.total += 1
                        mk_inv.add({k: v for k, v in mk.items() if k != "events"})
                for q in rec.get("clob_quotes", {}).values():
                    cq_inv.total += 1
                    cq_inv.add(q)

    print("\n" + "=" * 72)
    print("POLYMARKET — Feldinventar")
    line_inv.report("Zeilen-Ebene (_meta)")
    ev_inv.report("Event-Ebene (gamma_events[i], ohne markets[])")
    mk_inv.report("Market/Bucket-Ebene (markets[j], ohne events-Rückverweis)")
    cq_inv.report("CLOB-Quote-Ebene (clob_quotes[token_id])")


if __name__ == "__main__":
    main()
