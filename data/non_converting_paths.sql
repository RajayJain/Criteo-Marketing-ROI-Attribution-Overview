-- ==========================================================================
-- Non-Converting Paths Query
-- --------------------------------------------------------------------------
-- Finds every user who had impressions but never converted, and stitches
-- their full touchpoint history into one path ending in a "Null" outcome.
-- This is the counterfactual data the Markov chain needs to properly
-- estimate each channel's causal contribution, not just relative credit
-- among conversions.
-- ==========================================================================

DROP TABLE IF EXISTS non_converting_paths;

CREATE TABLE non_converting_paths AS
WITH non_converters AS (
    -- Users with at least one impression who never appear in fact_conversions.
    -- LEFT JOIN + IS NULL scales much better than NOT IN once you move to
    -- the full 16M-row dataset.
    SELECT DISTINCT i.uid
    FROM fact_impressions i
    LEFT JOIN fact_conversions c ON c.uid = i.uid
    WHERE c.uid IS NULL
),

touchpoints AS (
    SELECT
        i.uid,
        i.campaign_id,
        i.impression_ts,
        i.spend,
        ROW_NUMBER() OVER (PARTITION BY i.uid ORDER BY i.impression_ts) AS touch_position,
        COUNT(*) OVER (PARTITION BY i.uid) AS total_touches
    FROM fact_impressions i
    JOIN non_converters nc ON nc.uid = i.uid
),

dim_campaign_dedup AS (
    -- Same defensive dedup as journey_stitching.sql, in case dim_campaign
    -- ever ends up with duplicate campaign_id rows again.
    SELECT DISTINCT ON (campaign_id) campaign_id, pseudo_channel
    FROM dim_campaign
    ORDER BY campaign_id
),

touchpoints_with_channel AS (
    SELECT
        t.*,
        dc.pseudo_channel
    FROM touchpoints t
    JOIN dim_campaign_dedup dc ON dc.campaign_id = t.campaign_id
)

SELECT
    uid,
    total_touches,
    STRING_AGG(pseudo_channel, ' > ' ORDER BY touch_position) AS channel_path,
    SUM(spend)          AS total_journey_spend,
    MIN(impression_ts)  AS first_touch_ts,
    MAX(impression_ts)  AS last_touch_ts
FROM touchpoints_with_channel
GROUP BY uid, total_touches
ORDER BY uid;