SELECT campaign_id, COUNT(*)
FROM dim_campaign
GROUP BY campaign_id
HAVING COUNT(*) > 1
LIMIT 10;


DROP TABLE IF EXISTS dim_campaign_clean;

CREATE TABLE dim_campaign_clean AS
SELECT DISTINCT ON (campaign_id) campaign_id, pseudo_channel
FROM dim_campaign
ORDER BY campaign_id;

DROP TABLE dim_campaign;
ALTER TABLE dim_campaign_clean RENAME TO dim_campaign;