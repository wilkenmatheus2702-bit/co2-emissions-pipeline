-- Note: "1.0 *" forces real division (SQLite divides integers as integers).
-- Did economies grow while emissions fell? Compares the baseline year with the
-- latest year that has GDP data (GDP is published with a lag).
--   absolute: GDP up, CO2 down
--   relative: CO2 grew, but slower than GDP
--   none:     CO2 grew as fast as GDP or faster, or GDP did not grow
WITH gdp_year AS (
    SELECT MAX(year) AS year FROM emissions WHERE gdp_usd IS NOT NULL
),
pairs AS (
    SELECT
        b.country,
        b.iso_code,
        l.year     AS latest_year,
        b.gdp_usd  AS gdp_base,
        l.gdp_usd  AS gdp_last,
        b.co2_mt   AS co2_base,
        l.co2_mt   AS co2_last
    FROM emissions AS b
    JOIN gdp_year AS g
    JOIN emissions AS l ON l.iso_code = b.iso_code AND l.year = g.year
    WHERE b.year = :baseline_year
      AND l.population >= 1000000
      AND b.gdp_usd > 0 AND b.co2_mt > 0
      AND l.gdp_usd IS NOT NULL AND l.co2_mt IS NOT NULL
)
SELECT
    country,
    iso_code,
    :baseline_year                                  AS baseline_year,
    latest_year,
    ROUND(100.0 * (1.0 * gdp_last / gdp_base - 1), 1) AS gdp_change_pct,
    ROUND(100.0 * (1.0 * co2_last / co2_base - 1), 1) AS co2_change_pct,
    CASE
        WHEN gdp_last > gdp_base AND co2_last < co2_base THEN 'absolute'
        WHEN gdp_last > gdp_base
         AND 1.0 * gdp_last / gdp_base > 1.0 * co2_last / co2_base THEN 'relative'
        ELSE 'none'
    END                                             AS decoupling
FROM pairs
ORDER BY co2_change_pct;
