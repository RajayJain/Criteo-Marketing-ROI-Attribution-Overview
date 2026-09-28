/*SELECT 
    (SELECT COUNT(*) FROM fact_impressions) AS total_impressions,
    (SELECT COUNT(*) FROM fact_conversions) AS total_conversions,
    (SELECT COUNT(DISTINCT campaign_id) FROM dim_campaign) AS total_campaigns;
*/

/*WITH impression_stats AS (
    SELECT 
        dc.pseudo_channel,
        COUNT(fi.impression_id) AS total_impressions,
        SUM(fi.click) AS total_clicks,
        SUM(fi.spend) AS total_spend
    FROM fact_impressions fi
    JOIN dim_campaign dc ON fi.campaign_id = dc.campaign_id
    GROUP BY dc.pseudo_channel
),
conversion_stats AS (
    SELECT 
        dc.pseudo_channel,
        COUNT(fc.conversion_id) AS total_conversions
    FROM fact_conversions fc
    JOIN dim_campaign dc ON fc.campaign_id = dc.campaign_id
    GROUP BY dc.pseudo_channel
)
SELECT 
    i.pseudo_channel,
    i.total_impressions,
    i.total_clicks,
    ROUND(i.total_spend::numeric, 2) AS total_spend,
    COALESCE(c.total_conversions, 0) AS total_conversions,
    CASE 
        WHEN COALESCE(c.total_conversions, 0) = 0 THEN NULL 
        ELSE ROUND((i.total_spend / c.total_conversions)::numeric, 2) 
    END AS cost_per_acquisition
FROM impression_stats i
LEFT JOIN conversion_stats c ON i.pseudo_channel = c.pseudo_channel
ORDER BY total_spend DESC;
*/

-- ==========================================================================
-- Journey-Stitching Query
-- --------------------------------------------------------------------------
-- Builds the full ordered touchpoint path leading to each conversion.
-- Each user's journey is bounded by their PREVIOUS conversion (if any),
-- so touchpoints aren't double-counted across multiple purchases by the
-- same user. Output: one row per conversion, with a channel_path like
-- 'Channel A > Channel C > Channel B' ready for attribution modeling.
-- ==========================================================================

WITH conversions_ranked AS (
    -- Rank each user's conversions in time order, and grab the previous
    -- conversion timestamp so we know where this journey's window starts.
    SELECT
        conversion_id,
        uid,
        campaign_id            AS converting_campaign_id,
        conversion_ts,
        attributed_conversion,
        cpo,
        LAG(conversion_ts) OVER (
            PARTITION BY uid ORDER BY conversion_ts
        ) AS prev_conversion_ts
    FROM fact_conversions
),

journey_touchpoints AS (
    -- Pull every impression for this user that falls between the
    -- previous conversion (exclusive) and this conversion (inclusive).
    SELECT
        c.conversion_id,
        c.uid,
        c.conversion_ts,
        c.attributed_conversion,
        c.cpo,
        i.impression_id,
        i.campaign_id,
        i.impression_ts,
        i.click,
        i.spend,
        ROW_NUMBER() OVER (
            PARTITION BY c.conversion_id ORDER BY i.impression_ts
        ) AS touch_position,
        COUNT(*) OVER (PARTITION BY c.conversion_id) AS total_touches
    FROM conversions_ranked c
    JOIN fact_impressions i
        ON i.uid = c.uid
        AND i.impression_ts <= c.conversion_ts
        AND (
            c.prev_conversion_ts IS NULL
            OR i.impression_ts > c.prev_conversion_ts
        )
),

journey_with_channel AS (
    -- Attach the pseudo-channel label and first/last-touch flags.
    SELECT
        jt.*,
        dc.pseudo_channel,
        CASE WHEN touch_position = 1 THEN 1 ELSE 0 END              AS is_first_touch,
        CASE WHEN touch_position = total_touches THEN 1 ELSE 0 END  AS is_last_touch
    FROM journey_touchpoints jt
    JOIN dim_campaign dc ON dc.campaign_id = jt.campaign_id
)

-- Final output: one row per conversion, with the full stitched path.
SELECT
    conversion_id,
    uid,
    conversion_ts,
    attributed_conversion,
    cpo,
    total_touches,
    STRING_AGG(pseudo_channel, ' > ' ORDER BY touch_position)        AS channel_path,
    STRING_AGG(campaign_id::text, ' > ' ORDER BY touch_position)     AS campaign_path,
    SUM(spend)                                                       AS total_journey_spend,
    MIN(impression_ts)                                               AS first_touch_ts,
    MAX(impression_ts)                                               AS last_touch_ts
FROM journey_with_channel
GROUP BY conversion_id, uid, conversion_ts, attributed_conversion, cpo, total_touches
ORDER BY conversion_ts;


-- ==========================================================================
-- Bonus: quick first-touch vs last-touch revenue credit by channel
-- --------------------------------------------------------------------------
-- A fast sanity check you can run right after the query above, using the
-- same journey_with_channel logic - shows how differently first-touch and
-- last-touch attribution credit each channel, before you even build the
-- Python attribution models. Wrap the CTEs above around this if running
-- standalone, or save the main query as a view first (see note below).
-- ==========================================================================

-- SELECT
--     pseudo_channel,
--     COUNT(*) FILTER (WHERE is_first_touch = 1)  AS first_touch_conversions,
--     COUNT(*) FILTER (WHERE is_last_touch = 1)   AS last_touch_conversions
-- FROM journey_with_channel
-- WHERE attributed_conversion = 1
-- GROUP BY pseudo_channel
-- ORDER BY last_touch_conversions DESC;