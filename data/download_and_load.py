"""
download_and_load.py
---------------------
Step 1-2 of the Marketing Attribution & Campaign ROI project.

Downloads the Criteo Attribution Modeling for Bidding (CAMB) dataset,
loads it directly from compressed gzip into pandas, renames columns into 
project-friendly names, and pushes the cleaned tables into a Postgres 
star schema (fact_impressions, fact_conversions, dim_campaign, 
dim_pseudo_channel, dim_date).

Usage:
    python download_and_load.py --sample 200000   # dev/testing mode
    python download_and_load.py --db-url postgresql://user:pass@localhost:5432/attribution

Requirements:
    pip install requests pandas scikit-learn tqdm
"""

import argparse
from pathlib import Path

import pandas as pd
import requests
from tqdm import tqdm

# ----------------------------------------------------------------------
# Config
# ----------------------------------------------------------------------
# Fixed URL to use the reliable Hugging Face resolve path
DATASET_URL = "https://huggingface.co/datasets/criteo/criteo-attribution-dataset/resolve/main/criteo_attribution_dataset.tsv.gz"

DATA_DIR = Path("data")
RAW_ARCHIVE = DATA_DIR / "criteo_attribution_dataset.tsv.gz"

# The raw file ships with no header row. This is the documented column
# order from the Criteo README / AdKDD 2017 paper.
RAW_COLUMNS = [
    "timestamp", "uid", "campaign", "conversion", "conversion_timestamp",
    "conversion_id", "attribution", "click", "click_pos", "click_nb",
    "cost", "cpo", "time_since_last_click",
    "cat1", "cat2", "cat3", "cat4", "cat5", "cat6", "cat7", "cat8", "cat9",
]

# Renamed to read like a real marketing-analytics schema
COLUMN_RENAME = {
    "campaign": "campaign_id",
    "cost": "spend",
    "attribution": "attributed_conversion",
}

CAT_COLS = [c for c in RAW_COLUMNS if c.startswith("cat")]


# ----------------------------------------------------------------------
# Step 1: Download
# ----------------------------------------------------------------------
def download_dataset(url: str = DATASET_URL, dest: Path = RAW_ARCHIVE) -> Path:
    """Stream-download the dataset with a progress bar. Skips if already present."""
    DATA_DIR.mkdir(exist_ok=True)
    if dest.exists():
        print(f"[skip] {dest} already exists ({dest.stat().st_size / 1e6:.1f} MB)")
        return dest

    print(f"[download] {url}")
    with requests.get(url, stream=True, timeout=60) as r:
        r.raise_for_status()
        total = int(r.headers.get("content-length", 0))
        with open(dest, "wb") as f, tqdm(
            total=total, unit="B", unit_scale=True, desc=dest.name
        ) as bar:
            for chunk in r.iter_content(chunk_size=1024 * 1024):
                f.write(chunk)
                bar.update(len(chunk))
    return dest


# ----------------------------------------------------------------------
# Step 2: Load & clean
# ----------------------------------------------------------------------
def load_raw_data(nrows: int | None = None) -> pd.DataFrame:
    """
    Load the raw tsv.gz directly into pandas. 
    Reading directly from .gz saves ~2GB of disk space.
    """
    if not RAW_ARCHIVE.exists():
        raise FileNotFoundError(f"Missing {RAW_ARCHIVE}. Run without --skip-download first.")
        
    print(f"[load] reading {RAW_ARCHIVE} (nrows={nrows or 'all'})")
    df = pd.read_csv(
        RAW_ARCHIVE,
        sep="\t",
        header=None,
        names=RAW_COLUMNS,
        nrows=nrows,
        compression="gzip" # <-- Reads directly without unzipping
    )
    print(f"[load] {len(df):,} rows loaded")
    return df


def clean_and_rename(df: pd.DataFrame) -> pd.DataFrame:
    """Rename columns, fix dtypes, derive a real datetime from the relative timestamp."""
    df = df.rename(columns=COLUMN_RENAME)

    # --- FIX START: Force timestamps to numeric and drop bad rows ---
    # This handles the mixed types warning and any accidental header rows
    df["timestamp"] = pd.to_numeric(df["timestamp"], errors="coerce")
    df["conversion_timestamp"] = pd.to_numeric(df["conversion_timestamp"], errors="coerce")
    
    # Drop rows where timestamp couldn't be converted to a number (e.g., the header row)
    df = df.dropna(subset=["timestamp"]).copy()
    # --- FIX END ---

    # timestamps in the raw file are seconds elapsed since dataset start (day 0),
    # not real calendar dates. Anchor to an arbitrary 30-day window so the data
    # reads naturally in Power BI / SQL date logic later.
    origin = pd.Timestamp("2024-01-01")
    df["impression_ts"] = origin + pd.to_timedelta(df["timestamp"], unit="s")
    df["conversion_ts"] = df["conversion_timestamp"].apply(
        lambda s: origin + pd.Timedelta(seconds=s) if s >= 0 else pd.NaT
    )

    df["spend"] = df["spend"].astype(float)
    df["attributed_conversion"] = df["attributed_conversion"].astype(int)
    df["conversion"] = df["conversion"].astype(int)
    df["click"] = df["click"].astype(int)

    return df

# ----------------------------------------------------------------------
# Step 3: Pseudo-channels (the dataset has no named marketing channels)
# ----------------------------------------------------------------------
def cluster_pseudo_channels(df: pd.DataFrame, n_channels: int = 6, sample_size: int = 200_000) -> pd.DataFrame:
    """
    Cluster campaigns into pseudo-channels (Channel A-F) using the anonymized
    cat1-cat9 features, so the project can talk about "channels" the way a
    real marketing stack would. Documented as an explicit assumption in the
    README - see the project plan.
    """
    from sklearn.cluster import KMeans
    from sklearn.preprocessing import OrdinalEncoder

    campaign_profile = (
        df[["campaign_id"] + CAT_COLS]
        .drop_duplicates(subset="campaign_id")
        .set_index("campaign_id")
    )

    # --- FIX START: Force all categorical features to strings ---
    # This ensures the encoder gets a uniform data type
    campaign_profile[CAT_COLS] = campaign_profile[CAT_COLS].astype(str)
    # --- FIX END ---

    encoded = OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1).fit_transform(
        campaign_profile
    )

    fit_sample = encoded if len(encoded) <= sample_size else encoded[:sample_size]
    km = KMeans(n_clusters=n_channels, random_state=42, n_init=10).fit(fit_sample)
    labels = km.predict(encoded)

    channel_names = [chr(ord("A") + i) for i in range(n_channels)]
    campaign_profile["pseudo_channel"] = [f"Channel {channel_names[l]}" for l in labels]

    df = df.merge(
        campaign_profile[["pseudo_channel"]],
        left_on="campaign_id",
        right_index=True,
        how="left",
    )
    return df

# ----------------------------------------------------------------------
# Step 4: Build star-schema tables
# ----------------------------------------------------------------------
def build_star_schema(df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Split the flat dataframe into fact/dim tables ready to load into Postgres."""

    dim_campaign = (
        df[["campaign_id", "pseudo_channel"]]
        .drop_duplicates(subset="campaign_id")
        .reset_index(drop=True)
    )

    dim_pseudo_channel = (
        dim_campaign[["pseudo_channel"]]
        .drop_duplicates()
        .reset_index(drop=True)
        .rename_axis("channel_id")
        .reset_index()
    )

    all_dates = pd.concat([df["impression_ts"], df["conversion_ts"]]).dropna().dt.date.unique()
    dim_date = pd.DataFrame({"date": sorted(all_dates)})
    dim_date["day_of_week"] = pd.to_datetime(dim_date["date"]).dt.day_name()
    dim_date["week_number"] = pd.to_datetime(dim_date["date"]).dt.isocalendar().week

    fact_impressions = df[[
        "uid", "campaign_id", "impression_ts", "click", "click_pos", "click_nb", "spend",
    ]].reset_index(drop=True).rename_axis("impression_id").reset_index()

    fact_conversions = df[df["conversion"] == 1][[
        "uid", "campaign_id", "conversion_id", "conversion_ts",
        "attributed_conversion", "cpo", "time_since_last_click",
    ]].drop_duplicates(subset="conversion_id").reset_index(drop=True)

    return {
        "dim_campaign": dim_campaign,
        "dim_pseudo_channel": dim_pseudo_channel,
        "dim_date": dim_date,
        "fact_impressions": fact_impressions,
        "fact_conversions": fact_conversions,
    }


# ----------------------------------------------------------------------
# Step 5: Load into Postgres (Optional)
# ----------------------------------------------------------------------
def load_to_postgres(tables: dict[str, pd.DataFrame], db_url: str, chunksize: int = 50_000) -> None:
    try:
        from sqlalchemy import create_engine
    except ImportError:
        print("[error] SQLAlchemy not installed. Run: pip install sqlalchemy psycopg2-binary")
        return
        
    engine = create_engine(db_url)
    for name, table in tables.items():
        print(f"[db] writing {name} ({len(table):,} rows)")
        table.to_sql(name, engine, if_exists="replace", index=False, chunksize=chunksize, method="multi")
    print("[db] done")


# ----------------------------------------------------------------------
# Pipeline entrypoint
# ----------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Download and load the Criteo attribution dataset")
    parser.add_argument("--url", default=DATASET_URL, help="Override the dataset download URL")
    parser.add_argument("--db-url", default=None, help="SQLAlchemy Postgres URL, e.g. postgresql://user:pass@localhost:5432/attribution")
    parser.add_argument("--skip-download", action="store_true", help="Skip download, reuse existing data/ file")
    parser.add_argument("--sample", type=int, default=None, help="Load only N rows, for fast local testing")
    parser.add_argument("--n-channels", type=int, default=6, help="Number of pseudo-channels to cluster into")
    args = parser.parse_args()

    if not args.skip_download:
        download_dataset(args.url)

    df = load_raw_data(nrows=args.sample)
    df = clean_and_rename(df)
    df = cluster_pseudo_channels(df, n_channels=args.n_channels)
    tables = build_star_schema(df)

    for name, table in tables.items():
        print(f"  {name}: {table.shape}")

    if args.db_url:
        load_to_postgres(tables, args.db_url)
    else:
        out_dir = DATA_DIR / "star_schema_csv"
        out_dir.mkdir(exist_ok=True)
        for name, table in tables.items():
            table.to_csv(out_dir / f"{name}.csv", index=False)
        print(f"[skip] no --db-url given, wrote CSVs to {out_dir}/ instead")


if __name__ == "__main__":
    main()