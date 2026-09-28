<div align = "Center">
    <img src="data/criteo.png" alt="Netflix Logo" width="600"/>
</div>

# 🎯 Criteo Marketing Attribution & Campaign ROI

> An end-to-end marketing analytics project that turns ad-impression and conversion data into stitched customer journeys, multi-touch attribution insights, and a Power BI decision dashboard.

[![SQL](https://img.shields.io/badge/SQL-PostgreSQL-336791?logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![Python](https://img.shields.io/badge/Python-3.9%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Power BI](https://img.shields.io/badge/Power%20BI-Dashboard-F2C811?logo=powerbi&logoColor=111111)](https://powerbi.microsoft.com/)
[![Status](https://img.shields.io/badge/Project-Complete-2ea44f)](#-conclusion)
[![Analysis](https://img.shields.io/badge/Analysis-Multi--touch%20attribution-6f42c1)](#-methodology)
[![Markov](https://img.shields.io/badge/Model-Markov%20removal%20effect-7e57c2)](#markov-removal-effect-attribution)
[![Lift test](https://img.shields.io/badge/Test-Observational%20lift-0f766e)](#exposed-vs-unexposed-observational-lift)
[![Journeys](https://img.shields.io/badge/Conversion%20journeys-8%2C571-1d4ed8)](#-data-quality--validation)
[![Channels](https://img.shields.io/badge/Pseudo--channels-6-0284c7)](#-data-quality--validation)
[![Data quality](https://img.shields.io/badge/Data%20quality-Validated-059669)](#-data-quality--validation)
[![Period](https://img.shields.io/badge/Export%20window-Jan%202024-475569)](#-data-quality--validation)

![Criteo marketing attribution pipeline](data/attribution-pipeline.png)

## 📌 Project overview

Marketing channels rarely work in isolation. A customer may encounter several campaign touchpoints before converting, so assigning all credit to the last interaction can produce misleading budget decisions.

This project creates a reproducible attribution workflow that:

- 🧹 validates and deduplicates campaign mappings;
- 🧵 stitches ordered, conversion-bounded customer journeys in SQL;
- 🔗 builds both converting and non-converting path populations for multi-touch analysis;
- 📈 compares channel credit using a Markov removal-effect model;
- 🧪 measures **observational** exposed-vs-unexposed conversion-rate differences; and
- 📊 presents attribution and journey-depth results in Power BI.

## ✨ Dashboard preview

The included Power BI report contains an interactive dashboard with filters, KPI cards, a six-model credited-revenue comparison, a conversion-by-touch-count view, and a detailed results table.

![Markov attribution credit share by channel](data/markov-credit-share.png)
![](data/Criteo.png)

## 🗂️ Repository structure

```text
criteo-marketing-attribution/
├── data/
      ├──Criteo_Dash.pbix                     # Interactive Power BI dashboard
      ├── README.md
      ├── data_export.csv                       # Exported stitched conversion journeys
      ├── incrementality_results.csv            # Channel-level observational lift results
      ├── markov_results.csv                    # Markov removal-effect attribution results
      ├── incrementality_test.py                # Python two-proportion lift analysis
      ├── SQL_Queries/
      │   ├── Cleaning dim_campiagn.sql          # Campaign-mapping duplicate check and cleanup
      │   ├── Initial_query.sql                  # Journey-stitching query and first/last-touch check
      │   ├── journey_paths.sql                  # Materializes conversion-bounded journey paths
      │   └── non_converting_paths.sql           # Materializes paths for users who did not convert
      └── assets/
          ├── attribution-pipeline.png           # README process diagram
          └── markov-credit-share.png            # README results chart
          └── Final Power BI Dashboard           # Final Dashboard Glimpse
```

> **Tip:** For a production repository, rename `Cleaning dim_campiagn.sql` to `01_clean_dim_campaign.sql` when reorganizing files. The current spelling is retained above to match the supplied project file.

## 🧭 Methodology

```mermaid
flowchart LR
    A[Impression events] --> C[SQL journey stitching]
    B[Conversion events] --> C
    D[Campaign dimension] --> E[Campaign mapping QA]
    E --> C
    C --> F[Converting paths]
    C --> G[Non-converting paths]
    F --> H[Markov attribution]
    G --> H
    F --> I[Exposed vs. unexposed lift]
    G --> I
    H --> J[Power BI dashboard]
    I --> J
```

### 1. Campaign mapping quality

`Cleaning dim_campiagn.sql` first identifies duplicate `campaign_id` values. It then creates a one-row-per-campaign mapping with `DISTINCT ON (campaign_id)` before the original dimension is replaced. This avoids duplicated touchpoints and inflated aggregated spend after joins.

### 2. Conversion-bounded journey stitching

`journey_paths.sql` links impressions to each conversion for the same user, ordered by impression timestamp. For repeat purchasers, the journey window begins **after the user’s previous conversion** and ends at the current conversion. This prevents the same touchpoint being credited to multiple purchases.

Each output row contains a full channel sequence such as `Channel A > Channel C > Channel B`, touch count, journey spend, and first/last touch timestamps.

### 3. Non-converting paths

`non_converting_paths.sql` finds users with impressions but no conversion record, then aggregates each user’s ordered channel history. These paths provide the non-conversion population required for an absorbing `Null` outcome in a Markov-chain workflow.

### 4. Complementary channel signals

| Analysis | What it estimates | How to use it |
|---|---|---|
| Markov removal effect | Relative channel credit based on how conversion probability changes when a channel is removed from observed paths | Compare assist value across the journey |
| Exposed vs. unexposed test | Difference in conversion rates for users exposed to a channel versus users exposed to other channels | Prioritize hypotheses for a controlled experiment |

## 📊 Key results

### Markov removal-effect attribution

| Rank | Channel | Credit share | Credited revenue* |
|:---:|---|---:|---:|
| 1 | Channel F | 19.81% | 85.29 |
| 2 | Channel C | 19.68% | 84.72 |
| 3 | Channel A | 18.86% | 81.22 |
| 4 | Channel D | 15.87% | 68.32 |
| 5 | Channel B | 13.98% | 60.20 |
| 6 | Channel E | 11.80% | 50.80 |

\*Reported exactly as stored in `markov_results.csv`; confirm currency and revenue-definition conventions before using it in financial reporting.

Channels F and C receive a combined **39.5%** of model credit, making them high-priority channels to investigate alongside their spend, reach, frequency, and saturation curves.

### Exposed vs. unexposed observational lift

| Channel | Exposed conversion rate | Unexposed conversion rate | Relative lift | Difference | 95% CI for difference | p-value | Significant at 5%? |
|---|---:|---:|---:|---:|---:|---:|:---:|
| Channel A | 3.25% | 2.75% | +18.02% | +0.50 pp | +0.27 to +0.72 pp | <0.001 | ✅ |
| Channel C | 3.10% | 2.78% | +11.59% | +0.32 pp | +0.11 to +0.53 pp | 0.002 | ✅ |
| Channel B | 2.98% | 2.81% | +5.81% | +0.16 pp | −0.07 to +0.40 pp | 0.168 | ❌ |
| Channel F | 2.80% | 2.85% | −1.71% | −0.05 pp | −0.25 to +0.15 pp | 0.630 | ❌ |
| Channel E | 2.60% | 2.87% | −9.49% | −0.27 pp | −0.50 to −0.05 pp | 0.022 | ✅ |
| Channel D | 2.53% | 2.91% | −13.06% | −0.38 pp | −0.58 to −0.18 pp | <0.001 | ✅ |

> ⚠️ **Important interpretation:** this is an observational, correlational comparison—not a randomized incrementality experiment. Exposure is not randomly assigned, so selection bias and unobserved confounders may explain some or all of the observed differences. Do not interpret a significant result as causal proof or directly reallocate budget from it alone.

## ✅ Data quality & validation

The provided journey export was profiled before results were documented.

| Check | Result | Why it matters |
|---|---:|---|
| Stitched conversion-journey rows | 8,571 | Establishes the analysis population |
| Unique conversion IDs | 8,571 | No duplicate conversion rows in the export |
| Unique user IDs | 8,373 | Repeat conversions are retained as separate journeys |
| Pseudo-channels | 6 | Channel taxonomy is complete for the supplied export |
| Core-field nulls (`conversion_id`, `uid`, timestamp, path) | 0 | Key identifiers and path fields are populated |
| Path length = recorded `total_touches` | 8,571 / 8,571 | All exported paths reconcile to their touch counts |
| Touches per journey | 1–13; median 1; mean 1.40 | Journey depth is strongly concentrated in single-touch conversions |
| Conversion export window | 1–31 January 2024 | Sets the documented time scope |

Additional safeguards embedded in the SQL include campaign-dimension deduplication, chronological touch ordering, and conversion-to-conversion journey boundaries. Before a production refresh, add automated tests for referential integrity, timestamp validity, unexpected channel labels, negative spend, duplicate impression IDs, and reporting-period completeness.

## 🚀 Getting started

### Prerequisites

- PostgreSQL with `fact_impressions`, `fact_conversions`, and `dim_campaign` tables
- Python 3.9+ for the lift-analysis script
- Power BI Desktop to explore `Criteo_Dash.pbix`

### 1. Prepare the SQL layer

Run the queries in this order in a development or staging database:

```bash
psql "$DATABASE_URL" -f "SQL_Queries/Cleaning dim_campiagn.sql"
psql "$DATABASE_URL" -f "SQL_Queries/journey_paths.sql"
psql "$DATABASE_URL" -f "SQL_Queries/non_converting_paths.sql"
```

> ⚠️ The cleaning script drops and recreates `dim_campaign`; review its deterministic tie-breaking rule and back up production data before use.

### 2. Run the observational lift analysis

Install the required libraries:

```bash
python -m pip install pandas numpy scipy sqlalchemy psycopg2-binary
```

Run against PostgreSQL:

```bash
python incrementality_test.py \
  --db-url "postgresql://user:password@host:5432/attribution" \
  --out incrementality_results.csv
```

Or run from exported path files:

```bash
python incrementality_test.py \
  --conv-csv journey_paths.csv \
  --nonconv-csv non_converting_paths.csv \
  --out incrementality_results.csv
```

### 3. Explore the dashboard

Open `Criteo_Dash.pbix` with Power BI Desktop, refresh the model if needed, and use the dashboard filters to compare attribution models and touch-count distributions.

## 🔍 Findings & recommendations

- 🥇 **Validate Channel A first.** It combines a top-three Markov credit share (18.86%) with the strongest positive observed lift (+18.02%; +0.50 pp; statistically significant).
- 🤝 **Investigate the F/C pair.** Together they receive 39.5% of Markov credit, suggesting they are important within conversion paths. Their actual incremental value still needs an experiment.
- 🧭 **Do not equate model credit with causal ROI.** Channel F receives the most Markov credit but has no statistically significant positive observed lift in this comparison.
- 🧪 **Treat negative associations as diagnostic signals.** Channels D and E show statistically significant negative associations, which may reflect audience mix, sequencing, frequency, or confounding—not necessarily harmful media.
- 📉 **Design for short paths.** With a median of one touch per exported conversion journey, use path-depth segmentation before making broad multi-touch optimization claims.

## 🧱 Limitations

- The lift test is not randomized; it cannot establish causal incrementality.
- No geography field or randomized treatment/holdout assignment is available in the supplied materials.
- Markov attribution depends on observed paths and modeling assumptions; it is not a substitute for experimental measurement.
- The supplied files do not include the source code used to generate `markov_results.csv`, so the README documents that output but does not claim a fully reproducible Markov implementation.
- `credited_revenue` units should be validated against the source financial definition before external reporting.

## 🔮 Future scope

- **Causal measurement:** run a randomized geo-holdout, PSA, or ghost-ads experiment with pre-registered success metrics.
- **Bias reduction:** use propensity-score weighting/matching or doubly robust estimation as an interim observational analysis, with sensitivity checks.
- **Richer outcomes:** add revenue, margin, customer lifetime value, retention, and return/refund signals.
- **Media efficiency:** blend attribution results with spend, reach, frequency, and diminishing-return curves to estimate marginal ROAS.
- **Model maturity:** version and reproduce the Markov implementation; compare it with first-touch, last-touch, linear, time-decay, and data-driven models.
- **Data operations:** orchestrate automated SQL checks, freshness alerts, schema tests, and scheduled Power BI refreshes.
- **Privacy & governance:** document data lineage, retention, consent, and access controls for pseudonymous user-level data.

## 🏁 Conclusion

This project provides a credible foundation for multi-touch attribution: journeys are cleaned, bounded, ordered, and validated before being modeled and surfaced in Power BI. The key business takeaway is not a single “winner,” but a decision framework: use Markov results to understand path contribution, use observational lift to generate hypotheses, and use controlled experiments to establish true incrementality before making material budget changes.

---


# 🤝 Connect With Me  
## 👤 Author

**Rajay Jain**  
* **📧 Email**: jainrajay2001@gmail.com  
* **💼 LinkedIn**: [www.linkedin.com/in/rajay-ajay-jain-a3abb4168](https://www.linkedin.com/in/rajay-ajay-jain-a3abb4168)  
* **🐙 GitHub**: [https://github.com/RajayJain](https://github.com/RajayJain)  
### ⭐ If this project helped you, drop a star — it means a lot!


<img src="https://capsule-render.vercel.app/api?type=waving&color=gradient&customColorList=6,11,20&height=120&section=footer&text=Thanks%20for%20visiting!&fontSize=28&fontColor=ffffff" />

