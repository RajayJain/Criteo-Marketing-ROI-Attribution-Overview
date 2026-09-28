"""
markov_attribution.py
-----------------------
Step 5b of the Marketing Attribution & Campaign ROI project.

Builds an absorbing Markov chain from BOTH converting journeys (journey_paths)
and non-converting journeys (non_converting_paths), then computes each
channel's removal effect: how much the overall conversion probability drops
when that channel is taken out of the chain entirely. This is a real
counterfactual estimate, not just a relative split of existing conversions.

Usage:
    python markov_attribution.py --db-url postgresql://postgres:pass@localhost:5432/attribution
    python markov_attribution.py --conv-csv journey_paths.csv --nonconv-csv non_converting_paths.csv

Requirements:
    pip install pandas numpy sqlalchemy psycopg2-binary
"""

import argparse
from collections import defaultdict

import numpy as np
import pandas as pd
from sqlalchemy import create_engine


# ----------------------------------------------------------------------
# Load
# ----------------------------------------------------------------------
def load_table(db_url, csv_path, table_name):
    if db_url:
        engine = create_engine(db_url)
        df = pd.read_sql(f"SELECT * FROM {table_name}", engine)
    elif csv_path:
        df = pd.read_csv(csv_path)
    else:
        raise ValueError(f"Provide either --db-url or a CSV path for {table_name}")
    df["channels"] = df["channel_path"].str.split(" > ")
    return df


def load_data(args):
    df_conv = load_table(args.db_url, args.conv_csv, "journey_paths")
    df_conv["cpo"] = pd.to_numeric(df_conv["cpo"], errors="coerce")
    df_conv["attributed_conversion"] = pd.to_numeric(df_conv["attributed_conversion"], errors="coerce")
    df_conv = df_conv.dropna(subset=["cpo", "attributed_conversion"])
    df_conv = df_conv[df_conv["attributed_conversion"] == 1].copy()

    df_nonconv = load_table(args.db_url, args.nonconv_csv, "non_converting_paths")

    print(f"[load] {len(df_conv):,} converting journeys, {len(df_nonconv):,} non-converting journeys")
    return df_conv, df_nonconv


# ----------------------------------------------------------------------
# Build the transition count matrix
# ----------------------------------------------------------------------
def build_transition_counts(df_conv: pd.DataFrame, df_nonconv: pd.DataFrame):
    all_channels = set()
    for path in df_conv["channels"]:
        all_channels.update(path)
    for path in df_nonconv["channels"]:
        all_channels.update(path)
    channels = sorted(all_channels)
    states = ["Start"] + channels + ["Conversion", "Null"]

    counts = defaultdict(lambda: defaultdict(float))

    def add_sequence(seq):
        for a, b in zip(seq[:-1], seq[1:]):
            counts[a][b] += 1

    for path in df_conv["channels"]:
        add_sequence(["Start"] + path + ["Conversion"])
    for path in df_nonconv["channels"]:
        add_sequence(["Start"] + path + ["Null"])

    counts_df = pd.DataFrame(0.0, index=states, columns=states)
    for a, row in counts.items():
        for b, v in row.items():
            counts_df.loc[a, b] = v

    return counts_df, channels


# ----------------------------------------------------------------------
# Absorbing Markov chain math
# ----------------------------------------------------------------------
def conversion_probability(counts_df: pd.DataFrame) -> float:
    """
    Given a state-transition count matrix (rows=from, cols=to), compute the
    probability of being absorbed into 'Conversion' starting from 'Start',
    using the standard fundamental-matrix method for absorbing Markov chains:
        N = (I - Q)^-1        (Q = transient-to-transient transition probs)
        B = N @ R              (R = transient-to-absorbing transition probs)
    B[Start, Conversion] is the answer.
    """
    absorbing = ["Conversion", "Null"]
    transient = [s for s in counts_df.index if s not in absorbing]

    row_sums = counts_df.loc[transient].sum(axis=1)
    probs = counts_df.loc[transient].div(row_sums.replace(0, np.nan), axis=0).fillna(0)

    Q = probs[transient].values
    R = probs[absorbing].values
    n = len(transient)

    N = np.linalg.inv(np.eye(n) - Q)
    B = N @ R

    start_idx = transient.index("Start")
    conv_idx = absorbing.index("Conversion")
    return float(B[start_idx, conv_idx])


def remove_channel(counts_df: pd.DataFrame, channel: str) -> pd.DataFrame:
    """
    Removes a channel node from the chain: any traffic that would have
    flowed INTO this channel is redirected to 'Null' instead (representing
    the visitor dropping off with that channel unavailable), and the
    channel's row/column are dropped entirely.
    """
    modified = counts_df.copy()
    modified["Null"] = modified["Null"] + modified[channel]
    modified = modified.drop(index=channel, columns=channel)
    return modified


def compute_removal_effects(counts_df: pd.DataFrame, channels: list[str]) -> pd.Series:
    baseline = conversion_probability(counts_df)
    print(f"[markov] baseline Start -> Conversion probability: {baseline:.6f}")

    effects = {}
    for channel in channels:
        reduced = remove_channel(counts_df, channel)
        prob_without = conversion_probability(reduced)
        effects[channel] = max(baseline - prob_without, 0.0)  # guard tiny negative floating-point noise

    return pd.Series(effects, name="removal_effect")


# ----------------------------------------------------------------------
# Convert removal effects into credited revenue
# ----------------------------------------------------------------------
def credit_from_removal_effects(effects: pd.Series, total_revenue: float) -> pd.DataFrame:
    total_effect = effects.sum()
    share = effects / total_effect if total_effect > 0 else effects
    credited_revenue = share * total_revenue

    table = pd.DataFrame({
        "removal_effect": effects,
        "credit_share": share,
        "credited_revenue": credited_revenue,
    }).sort_values("credited_revenue", ascending=False)
    return table


# ----------------------------------------------------------------------
# Entrypoint
# ----------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Markov chain removal-effect attribution")
    parser.add_argument("--db-url", default=None, help="Postgres URL (reads both tables from the DB)")
    parser.add_argument("--conv-csv", default=None, help="CSV export of journey_paths")
    parser.add_argument("--nonconv-csv", default=None, help="CSV export of non_converting_paths")
    parser.add_argument("--out", default="markov_results.csv", help="Where to save the results table")
    args = parser.parse_args()

    df_conv, df_nonconv = load_data(args)
    counts_df, channels = build_transition_counts(df_conv, df_nonconv)
    print(f"[markov] {len(channels)} channels found: {channels}")

    effects = compute_removal_effects(counts_df, channels)
    total_revenue = df_conv["cpo"].sum()
    results = credit_from_removal_effects(effects, total_revenue)

    print("\nMarkov chain removal-effect results:\n")
    print(results.round(4))

    results.to_csv(args.out)
    print(f"\n[save] results written to {args.out}")


if __name__ == "__main__":
    main()
