-- Focus countries: latest year compared with the baseline year.
WITH latest AS (
    SELECT MAX(year) AS year FROM emissions WHERE co2_mt IS NOT NULL
)
SELECT
    l.country,
    l.iso_code,
    :baseline_year                                    AS baseline_year,
    l.year                                            AS latest_year,
    ROUND(b.co2_mt, 1)                                AS co2_baseline_mt,
    ROUND(l.co2_mt, 1)                                AS co2_latest_mt,
    ROUND(l.change_vs_baseline_pct, 1)                AS co2_change_pct,
    ROUND(b.co2_per_capita_t, 2)                      AS per_capita_baseline_t,
    ROUND(l.co2_per_capita_t, 2)                      AS per_capita_latest_t,
    ROUND(l.coal_share_pct, 1)                        AS coal_share_pct,
    ROUND(l.oil_share_pct, 1)                         AS oil_share_pct,
    ROUND(l.gas_share_pct, 1)                         AS gas_share_pct
FROM emissions AS l
JOIN latest AS y ON l.year = y.year
JOIN focus_countries AS f ON f.iso_code = l.iso_code
LEFT JOIN emissions AS b ON b.iso_code = l.iso_code AND b.year = :baseline_year
ORDER BY co2_change_pct;
