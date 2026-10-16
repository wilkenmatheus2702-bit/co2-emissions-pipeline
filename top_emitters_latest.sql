-- Top 10 emitting countries in the latest year with data,
-- and each one's share of the total emitted by all countries that year.
WITH latest AS (
    SELECT MAX(year) AS year FROM emissions WHERE co2_mt IS NOT NULL
)
SELECT
    RANK() OVER (ORDER BY e.co2_mt DESC)                   AS rank,
    e.country,
    e.iso_code,
    e.year,
    ROUND(e.co2_mt, 1)                                     AS co2_mt,
    ROUND(100.0 * e.co2_mt / SUM(e.co2_mt) OVER (), 1)     AS share_of_total_pct
FROM emissions AS e
JOIN latest AS l ON e.year = l.year
WHERE e.co2_mt IS NOT NULL
ORDER BY rank
LIMIT 10;
