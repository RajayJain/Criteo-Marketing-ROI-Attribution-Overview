DROP TABLE IF EXISTS journey_paths;

CREATE TABLE journey_paths AS
WITH conversions_ranked AS (
    SELECT
        conversion_id, uid,
        campaign_id AS converting_campaign_id,
        conversion_ts, attributed_conversion, cpo,
        LAG(conversion_ts) OVER (PARTITION BY uid ORDER BY conversion_ts) AS prev_conversion_ts
    FROM fact_conversions
),
journey_touchpoints AS (
    SELECT
        c.conversion_id, c.uid, c.conversion_ts, c.attributed_conversion, c.cpo,
        i.impression_id, i.campaign_id, i.impression_ts, i.click, i.spend,
        ROW_NUMBER() OVER (PARTITION BY c.conversion_id ORDER BY i.impression_ts) AS touch_position,
        COUNT(*) OVER (PARTITION BY c.conversion_id) AS total_touches
    FROM conversions_ranked c
    JOIN fact_impressions i
        ON i.uid = c.uid
        AND i.impression_ts <= c.conversion_ts
        AND (c.prev_conversion_ts IS NULL OR i.impression_ts > c.prev_conversion_ts)
),
dim_campaign_dedup AS (
    -- defensive: guarantees one row per campaign_id no matter what's in the table
    SELECT DISTINCT ON (campaign_id) campaign_id, pseudo_channel
    FROM dim_campaign
    ORDER BY campaign_id
),
journey_with_channel AS (
    SELECT
        jt.*,
        dc.pseudo_channel,
        CASE WHEN touch_position = 1 THEN 1 ELSE 0 END AS is_first_touch,
        CASE WHEN touch_position = total_touches THEN 1 ELSE 0 END AS is_last_touch
    FROM journey_touchpoints jt
    JOIN dim_campaign_dedup dc ON dc.campaign_id = jt.campaign_id
)
SELECT
    conversion_id, uid, conversion_ts, attributed_conversion, cpo, total_touches,
    STRING_AGG(pseudo_channel, ' > ' ORDER BY touch_position) AS channel_path,
    STRING_AGG(campaign_id::text, ' > ' ORDER BY touch_position) AS campaign_path,
    SUM(spend) AS total_journey_spend,
    MIN(impression_ts) AS first_touch_ts,
    MAX(impression_ts) AS last_touch_ts
FROM journey_with_channel
GROUP BY conversion_id, uid, conversion_ts, attributed_conversion, cpo, total_touches
ORDER BY conversion_ts;