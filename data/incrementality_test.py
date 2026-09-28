"""
incrementality_test.py
------------------------
Step 6 of the Marketing Attribution & Campaign ROI project.

IMPORTANT - what this test actually measures:
This dataset has no geography field and no designed randomized experiment,
so a true geo-holdout or PSA/ghost-ad incrementality test isn't possible
here. Instead, this script runs an EXPOSED vs. UNEXPOSED comparison: for a
given channel, users who saw it vs. users who saw ads from other channels
but never that one. This measures OBSERVATIONAL / CORRELATIONAL lift, not
proven causal incrementality - exposed users may differ from unexposed
users in ways that also affect conversion (selection bias). A real
production test would use a randomized geo-holdout or ghost-ads design.
State this limitation explicitly in your README - it's a strength, not a
weakness, to be clear about it.

Usage:
    python incrementality_test.py --db-url postgresql://postgres:pass@localhost:5432/attribution
    python incrementality_test.py --conv-csv journey_paths.csv --nonconv-csv non_converting_paths.csv
    python incrementality_test.py --db-url ... --channel "Channel A"   # test one channel only

Requirements:
    pip install pandas numpy scipy sqlalchemy psycopg2-binary
"""

import argparse

import numpy as np
import pandas as pd
from scipy.stats import norm
from sqlalchemy import create_engine


# ----------------------------------------------------------------------
# Load & combine into one user-level population
# ----------------------------------------------------------------------
def load_table(db_url, csv_path, table_name):
    if db_url:
        engine = create_engine(db_url)
        df = pd.read_sql(f"SELECT * FROM {table_name}", engine)
    elif csv_path:
        df = pd.read_csv(csv_path)
    else:
        raise ValueError(f"Provide either --db-url or a CSV path for {table_name}")
    df["channels"] = df["channel_path"].str.split(" > ").apply(set)
    return df


def build_population(args) -> pd.DataFrame:
    df_conv = load_table(args.db_url, args.conv_csv, "journey_paths")
    df_conv["attributed_conversion"] = pd.to_numeric(df_conv["attributed_conversion"], errors="coerce")
    df_conv = df_conv.dropna(subset=["attributed_conversion"])
    df_conv = df_conv[df_conv["attributed_conversion"] == 1]
    conv_pop = df_conv[["uid", "channels"]].copy()
    conv_pop["converted"] = 1

    df_nonconv = load_table(args.db_url, args.nonconv_csv, "non_converting_paths")
    nonconv_pop = df_nonconv[["uid", "channels"]].copy()
    nonconv_pop["converted"] = 0

    population = pd.concat([conv_pop, nonconv_pop], ignore_index=True)
    print(f"[load] population: {len(population):,} users "
          f"({conv_pop.shape[0]:,} converted, {nonconv_pop.shape[0]:,} did not)")
    return population


# ----------------------------------------------------------------------
# Two-proportion z-test for one channel
# ----------------------------------------------------------------------
def test_channel_lift(population: pd.DataFrame, channel: str) -> dict:
    exposed_mask = population["channels"].apply(lambda s: channel in s)

    n1 = int(exposed_mask.sum())
    x1 = int(population.loc[exposed_mask, "converted"].sum())
    n2 = int((~exposed_mask).sum())
    x2 = int(population.loc[~exposed_mask, "converted"].sum())

    p1 = x1 / n1 if n1 else 0.0
    p2 = x2 / n2 if n2 else 0.0

    pooled_p = (x1 + x2) / (n1 + n2)
    se_pooled = np.sqrt(pooled_p * (1 - pooled_p) * (1 / n1 + 1 / n2))
    z_stat = (p1 - p2) / se_pooled if se_pooled > 0 else 0.0
    p_value = 2 * (1 - norm.cdf(abs(z_stat)))

    # 95% CI on the difference in proportions (unpooled SE, standard formula)
    se_diff = np.sqrt(p1 * (1 - p1) / n1 + p2 * (1 - p2) / n2)
    diff = p1 - p2
    ci_low = diff - 1.96 * se_diff
    ci_high = diff + 1.96 * se_diff

    lift_pct = (diff / p2 * 100) if p2 > 0 else float("nan")

    return {
        "channel": channel,
        "exposed_n": n1,
        "exposed_conv_rate": p1,
        "unexposed_n": n2,
        "unexposed_conv_rate": p2,
        "lift_pct": lift_pct,
        "diff_pct_points": diff * 100,
        "ci_95_low": ci_low * 100,
        "ci_95_high": ci_high * 100,
        "z_stat": z_stat,
        "p_value": p_value,
        "significant_at_05": p_value < 0.05,
    }


def run_all_channels(population: pd.DataFrame) -> pd.DataFrame:
    all_channels = sorted(set().union(*population["channels"]))
    results = [test_channel_lift(population, ch) for ch in all_channels]
    df_results = pd.DataFrame(results).sort_values("lift_pct", ascending=False)
    return df_results


# ----------------------------------------------------------------------
# Entrypoint
# ----------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Exposed vs. unexposed observational lift test per channel")
    parser.add_argument("--db-url", default=None)
    parser.add_argument("--conv-csv", default=None, help="CSV export of journey_paths")
    parser.add_argument("--nonconv-csv", default=None, help="CSV export of non_converting_paths")
    parser.add_argument("--channel", default=None, help="Test just this one channel instead of all")
    parser.add_argument("--out", default="incrementality_results.csv")
    args = parser.parse_args()

    population = build_population(args)

    if args.channel:
        result = test_channel_lift(population, args.channel)
        print(f"\nLift test for {args.channel}:\n")
        for k, v in result.items():
            print(f"  {k}: {v}")
        results_df = pd.DataFrame([result])
    else:
        results_df = run_all_channels(population)
        print("\nObservational lift test - all channels:\n")
        pd.set_option("display.width", 140)
        print(results_df.round(4))

    results_df.to_csv(args.out, index=False)
    print(f"\n[save] results written to {args.out}")
    print("\n[reminder] this is observational/correlational lift, not a randomized incrementality "
          "test - see the docstring at the top of this file for why.")


if __name__ == "__main__":
    main()
