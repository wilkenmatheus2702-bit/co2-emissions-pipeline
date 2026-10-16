-- Per-capita CO2 ranking in the latest year (countries with 1M+ people).
-- Returns the top 10 plus every focus country, wherever it ranks.
WITH latest AS (
    SELECT MAX(year) AS year FROM emissions WHERE co2_mt IS NOT NULL
),
ranked AS (
    SELECT
        e.country,
        e.iso_code,
        e.year,
        e.co2_per_capita_t,
        RANK() OVER (ORDER BY e.co2_per_capita_t DESC) AS rank,
        COUNT(*) OVER ()                               AS ranked_countries
    FROM emissions AS e
    JOIN latest AS l ON e.year = l.year
    WHERE e.population >= 1000000
      AND e.co2_per_capita_t IS NOT NULL
)
SELECT
    r.rank,
    r.country,
    r.iso_code,
    r.year,
    ROUND(r.co2_per_capita_t, 2)                         AS co2_per_capita_t,
    r.ranked_countries,
    CASE WHEN f.iso_code IS NULL THEN 0 ELSE 1 END       AS is_focus
FROM ranked AS r
LEFT JOIN focus_countries AS f ON f.iso_code = r.iso_code
WHERE r.rank <= 10 OR f.iso_code IS NOT NULL
ORDER BY r.rank;
