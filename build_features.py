"""
AP 3.1 — Analysis-Zone (Gold): Silver -> ML-ready Feature-Tabelle.

Grain: 1 Zeile = (city, target_date, bucket) = binaere Klassifikationsinstanz.
Label `y` = offizielles Markt-Ergebnis (label_is_winner_official).

Leakage-Regel (U2): jedes Feature muss zum D2-As-of-Zeitpunkt (D-1 23:59 lokal)
wissbar gewesen sein. Forecast-Features stammen aus dem as-of-Forecast des Silver;
das Vortages-Ist (D-1) ist zum Cut lokal abgeschlossen (dokumentierte Fussnote:
unsere Pipeline erfasst es erst D+1, operativ ist es am Abend von D-1 bekannt).

Marktpreise (`market_p`, `clob_mid`) sind KEINE Modell-Features (U3) — sie dienen
nur der Baseline "Markt als Praediktor" und dem Modell-vs-Markt-Vergleich.

Output (idempotenter Full-Rebuild aus Silver):
  data/processed/analysis.duckdb          Tabelle feature_table
  data/processed/analysis/feature_table/  Parquet, Partition city

Aufruf:  python build_features.py
"""

from __future__ import annotations

import datetime as dt
import logging
import math

import duckdb

import config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger("build_features")

SILVER = config.PROJECT_ROOT / "data" / "processed" / "silver.duckdb"
DB_PATH = config.PROJECT_ROOT / "data" / "processed" / "analysis.duckdb"
PARQUET_DIR = config.PROJECT_ROOT / "data" / "processed" / "analysis" / "feature_table"


def main() -> None:
    con = duckdb.connect(str(DB_PATH))
    con.execute(f"ATTACH '{SILVER}' AS silver (READ_ONLY)")

    con.execute("""
    CREATE OR REPLACE TABLE feature_table AS
    WITH s AS (SELECT * FROM silver.market_bucket_daily),
    -- Vortages-Ist je (city, Kalendertag): zum As-of-Cut lokal abgeschlossen (U2)
    obs AS (SELECT DISTINCT city, target_date, observed_max_c
            FROM s WHERE observed_max_c IS NOT NULL),
    -- Breite der inneren Buckets je Stadt (fuer Randbucket-Imputation, U6)
    width AS (SELECT city, MEDIAN(bucket_high_native - bucket_low_native + 1) *
                     CASE WHEN ANY_VALUE(temperature_unit) = 'fahrenheit'
                          THEN 5.0/9.0 ELSE 1.0 END AS inner_width_c
              FROM s WHERE bucket_kind IN ('exact','range') GROUP BY city)
    SELECT
        -- Schluessel + Label
        s.city, s.target_date, s.bucket_label,
        s.label_is_winner_official                             AS y,
        -- Markt (nur Baseline/Vergleich, U3 - NICHT als Modell-Feature verwenden)
        s.yes_price_norm                                       AS market_p,
        s.clob_mid,
        -- Bucket-Geometrie
        s.bucket_mid_c                                         AS f_bucket_mid_c,
        COALESCE((s.bucket_high_native - s.bucket_low_native + 1) *
                 CASE WHEN s.temperature_unit = 'fahrenheit' THEN 5.0/9.0 ELSE 1.0 END,
                 w.inner_width_c)                              AS f_bucket_width_c,
        s.bucket_kind IN ('below','above')                     AS f_bucket_is_edge,
        -- Forecast (as-of D-1, aus Silver)
        s.forecast_max_c                                       AS f_fc_max_c,
        s.forecast_max_c - s.bucket_mid_c                      AS f_dist_fc,
        ABS(s.forecast_max_c - s.bucket_mid_c)                 AS f_absdist_fc,
        s.forecast_max_c - s.forecast_min_c                    AS f_fc_span,
        -- Persistenz (Vortag)
        o.observed_max_c                                       AS f_prevday_obs_c,
        o.observed_max_c - s.bucket_mid_c                      AS f_dist_prevday,
        s.forecast_max_c - o.observed_max_c                    AS f_trend,
        -- Saisonalitaet (Jahreszyklus, stetig)
        SIN(2 * PI() * DAYOFYEAR(s.target_date) / 365.25)      AS f_doy_sin,
        COS(2 * PI() * DAYOFYEAR(s.target_date) / 365.25)      AS f_doy_cos,
        -- Kontrolle/QS (nicht fuers Modell)
        s.source, s.flag_partial_day, s.flag_overround_outlier,
        s.n_snapshots_pre_asof, s.hours_to_event_end
    FROM s
    LEFT JOIN obs o  ON o.city = s.city AND o.target_date = s.target_date - INTERVAL 1 DAY
    LEFT JOIN width w ON w.city = s.city
    WHERE s.label_is_winner_official IS NOT NULL          -- nur gelabelte Tage (U4)
      AND s.forecast_max_c IS NOT NULL                    -- Kern-Feature Pflicht (U5)
      AND o.observed_max_c IS NOT NULL                    -- Kern-Feature Pflicht (U5)
    """)

    # ---------------- QS-Checks (analog Silver: hart, nicht kosmetisch) ----------------
    q = lambda sql: con.execute(sql).fetchone()[0]
    n_rows = q("SELECT COUNT(*) FROM feature_table")
    n_days = q("SELECT COUNT(DISTINCT city || target_date) FROM feature_table")
    dropped = q(f"""SELECT COUNT(DISTINCT city || target_date) FROM silver.market_bucket_daily
                    WHERE label_is_winner_official IS NOT NULL""") - n_days
    dupes = q("""SELECT COUNT(*) FROM (SELECT city, target_date, bucket_label
                 FROM feature_table GROUP BY 1,2,3 HAVING COUNT(*) > 1)""")
    bad_label = q("""SELECT COUNT(*) FROM (SELECT city, target_date FROM feature_table
                     GROUP BY 1,2 HAVING SUM(y::INT) <> 1)""")
    nulls = q("""SELECT COUNT(*) FROM feature_table
                 WHERE f_dist_fc IS NULL OR f_dist_prevday IS NULL OR f_trend IS NULL
                    OR f_bucket_width_c IS NULL OR market_p IS NULL""")

    PARQUET_DIR.mkdir(parents=True, exist_ok=True)
    con.execute(f"""COPY feature_table TO '{PARQUET_DIR}'
                    (FORMAT PARQUET, PARTITION_BY (city), OVERWRITE_OR_IGNORE)""")
    con.close()

    logger.info("feature_table: %d Zeilen | %d City-Days (%d gelabelte Tage ohne Kern-Features verworfen)",
                n_rows, n_days, dropped)
    logger.info("QS: pk_dupes=%d | tage_ohne_genau_1_label=%d | kern_feature_nulls=%d",
                dupes, bad_label, nulls)
    if dupes or bad_label or nulls:
        raise SystemExit("QS check failed - siehe Log")
    logger.info("wrote %s (feature_table) + parquet unter %s", DB_PATH, PARQUET_DIR)


if __name__ == "__main__":
    main()
