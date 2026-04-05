"""
analyze_era5.py
===============
Process ERA5 reanalysis data to extract Indian climate-zone statistics.

Supports two modes:
1) Yearly mode (recommended): read one downloaded file per year from
     era5_data/yearly/ and aggregate to climatology using mean or median.
2) Single-file mode: read one NetCDF/ZIP source file.

Outputs:
    - data/era5/summary/era5_zone_statistics_by_year.csv
    - data/era5/summary/era5_zone_statistics_climatology.csv
    - data/era5/summary/era5_zone_statistics.csv (same as climatology for compatibility)
    - artifacts/plots/era5_zone_distributions_latest.png
"""

import argparse
import os
import re
import sys
import zipfile

import numpy as np
import pandas as pd
import xarray as xr
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ERA5_ARCHIVE_PATH = "era5_india_summer.nc"
ERA5_EXTRACT_DIR = "era5_data"
ERA5_YEARLY_DIR = os.path.join("era5_data", "yearly")
ERA5_TEMP_EXTRACT_ROOT = os.path.join("era5_data", "extracted")
ERA5_SUMMARY_DIR = os.path.join("data", "era5", "summary")
ERA5_PLOTS_DIR = os.path.join("artifacts", "plots")

# ============================================================
#  Zone Bounding Boxes (lat/lon)
# ============================================================
ZONE_BOXES = {
    "Hot_Dry": {
        "lat": (20.0, 30.0),
        "lon": (68.0, 78.0),
        "states": "Rajasthan, Gujarat, MP",
    },
    "Hot_Humid": {
        "lat": (8.0, 20.0),
        "lon": (74.0, 88.0),
        "states": "Kerala, TN coast, AP coast, Odisha, WB",
    },
    "Semi_Arid": {
        "lat": (13.0, 21.0),
        "lon": (74.0, 82.0),
        "states": "Karnataka, Telangana, Maharashtra, TN interior",
    },
    "Composite": {
        "lat": (24.0, 32.0),
        "lon": (74.0, 88.0),
        "states": "Delhi, UP, Bihar, Haryana, Punjab",
    },
    "Highland": {
        "lat": (25.0, 35.0),
        "lon": (76.0, 97.0),
        "states": "Himachal, Uttarakhand, Northeast",
    },
}

# MRT offset range estimation (solar radiation → tr_offset)
# tr_offset = tdb + (ssrd_factor * solar_radiation)
# This is a rough empirical approximation; the actual offset depends
# on surface albedo, wind, and clothing.


def dewpoint_to_rh(tdb: np.ndarray, tdew: np.ndarray) -> np.ndarray:
    """Convert dewpoint + air temperature to relative humidity (Magnus formula)."""
    e  = 6.112 * np.exp(17.67 * tdew / (tdew + 243.5))
    es = 6.112 * np.exp(17.67 * tdb  / (tdb  + 243.5))
    rh = 100.0 * (e / es)
    return np.clip(rh, 0.0, 100.0)


def infer_year(filepath: str) -> int:
    """Infer year from filename, return -1 if missing."""
    match = re.search(r"(19|20)\d{2}", os.path.basename(filepath))
    return int(match.group(0)) if match else -1


def list_input_files(yearly_dir: str, single_file: str) -> tuple:
    """Return a sorted list of ERA5 input files and selected mode."""
    if os.path.isdir(yearly_dir):
        yearly_files = [
            os.path.join(yearly_dir, f)
            for f in os.listdir(yearly_dir)
            if f.lower().endswith(".nc")
        ]
        if yearly_files:
            yearly_files.sort(key=lambda p: (infer_year(p), p))
            return yearly_files, "yearly"

    if os.path.exists(single_file):
        return [single_file], "single"

    instant_path = os.path.join(ERA5_EXTRACT_DIR, "data_stream-oper_stepType-instant.nc")
    accum_path = os.path.join(ERA5_EXTRACT_DIR, "data_stream-oper_stepType-accum.nc")
    if os.path.exists(instant_path) and os.path.exists(accum_path):
        return [single_file], "split"

    raise FileNotFoundError(
        "No ERA5 data found. Use download_era5.py first or place yearly files in "
        f"{yearly_dir}"
    )


def _open_era5_dataset(filepath: str, allow_global_split: bool) -> xr.Dataset:
    """Open ERA5 data from split files, ZIP archives, or direct NetCDF."""
    if allow_global_split:
        instant_path = os.path.join(ERA5_EXTRACT_DIR, "data_stream-oper_stepType-instant.nc")
        accum_path = os.path.join(ERA5_EXTRACT_DIR, "data_stream-oper_stepType-accum.nc")
        if os.path.exists(instant_path) and os.path.exists(accum_path):
            print(f"  Using split ERA5 files in {ERA5_EXTRACT_DIR}/")
            ds_instant = xr.open_dataset(instant_path)
            ds_accum = xr.open_dataset(accum_path)
            ds = xr.merge([ds_instant, ds_accum], compat="override")
            if "valid_time" in ds.coords and "time" not in ds.coords:
                ds = ds.rename({"valid_time": "time"})
            return ds

    if zipfile.is_zipfile(filepath):
        base_name = os.path.splitext(os.path.basename(filepath))[0]
        extract_dir = os.path.join(ERA5_TEMP_EXTRACT_ROOT, base_name)
        os.makedirs(extract_dir, exist_ok=True)
        print(f"  Detected ZIP archive; extracting to {extract_dir}")

        with zipfile.ZipFile(filepath, "r") as zf:
            members = [m for m in zf.namelist() if m.endswith(".nc")]
            if not members:
                raise FileNotFoundError("No .nc members found inside ERA5 ZIP archive")
            for member in members:
                target_path = os.path.join(extract_dir, member)
                needs_extract = (not os.path.exists(target_path))
                if os.path.exists(target_path) and os.path.getsize(target_path) == 0:
                    os.remove(target_path)
                    needs_extract = True
                if needs_extract:
                    zf.extract(member, path=extract_dir)

        instant_path = os.path.join(extract_dir, "data_stream-oper_stepType-instant.nc")
        accum_path = os.path.join(extract_dir, "data_stream-oper_stepType-accum.nc")
        if os.path.exists(instant_path) and os.path.exists(accum_path):
            ds_instant = xr.open_dataset(instant_path)
            ds_accum = xr.open_dataset(accum_path)
            ds = xr.merge([ds_instant, ds_accum], compat="override")
        else:
            nc_files = [
                os.path.join(extract_dir, f)
                for f in os.listdir(extract_dir)
                if f.endswith(".nc")
            ]
            if not nc_files:
                raise FileNotFoundError("No extracted .nc files found")
            ds = xr.open_dataset(nc_files[0])
    else:
        ds = xr.open_dataset(filepath)

    if "valid_time" in ds.coords and "time" not in ds.coords:
        ds = ds.rename({"valid_time": "time"})

    return ds


def load_and_prepare(filepath: str, allow_global_split: bool, verbose: bool = True) -> xr.Dataset:
    """Load ERA5 source, convert units, and compute derived fields."""
    print(f"Loading {filepath}...")
    ds = _open_era5_dataset(filepath, allow_global_split=allow_global_split)

    if verbose:
        print(f"  Variables: {list(ds.data_vars)}")
        if "time" in ds.coords:
            print(f"  Time range: {ds.time.values[0]} to {ds.time.values[-1]}")
        else:
            print("  WARNING: No time coordinate found")
        print(f"  Lat range: {float(ds.latitude.min())} to {float(ds.latitude.max())}")
        print(f"  Lon range: {float(ds.longitude.min())} to {float(ds.longitude.max())}")

    ds["t2m_c"] = ds["t2m"] - 273.15
    ds["d2m_c"] = ds["d2m"] - 273.15
    ds["rh"] = dewpoint_to_rh(ds["t2m_c"], ds["d2m_c"])
    ds["wind_speed"] = np.sqrt(ds["u10"]**2 + ds["v10"]**2)

    if "ssrd" in ds:
        ds["solar_wm2"] = ds["ssrd"] / (3.0 * 3600.0)
        ds["tr_offset_est"] = ds["solar_wm2"] * 0.012
    else:
        print("  WARNING: ssrd not in dataset, MRT offset estimation skipped")

    print(f"  Computed: t2m_c, d2m_c, rh, wind_speed")
    return ds


def extract_zone_stats(ds: xr.Dataset, zone_name: str, box: dict) -> dict:
    """Extract P5/P95 climate statistics for one zone."""
    lat_min, lat_max = box["lat"]
    lon_min, lon_max = box["lon"]

    zone_ds = ds.sel(
        latitude=slice(lat_max, lat_min),
        longitude=slice(lon_min, lon_max),
    )

    tdb  = zone_ds["t2m_c"].values.flatten()
    rh   = zone_ds["rh"].values.flatten()
    wind = zone_ds["wind_speed"].values.flatten()

    mask = ~(np.isnan(tdb) | np.isnan(rh) | np.isnan(wind))
    tdb, rh, wind = tdb[mask], rh[mask], wind[mask]

    working = tdb > 15.0
    tdb, rh, wind = tdb[working], rh[working], wind[working]

    if len(tdb) == 0:
        return {
            "zone": zone_name,
            "states": box["states"],
            "n_samples": 0,
            "tdb_mean": np.nan,
            "tdb_std": np.nan,
            "tdb_p5": np.nan,
            "tdb_p25": np.nan,
            "tdb_p50": np.nan,
            "tdb_p75": np.nan,
            "tdb_p95": np.nan,
            "tdb_max": np.nan,
            "rh_mean": np.nan,
            "rh_std": np.nan,
            "rh_p5": np.nan,
            "rh_p50": np.nan,
            "rh_p95": np.nan,
            "wind_mean": np.nan,
            "wind_p5": np.nan,
            "wind_p50": np.nan,
            "wind_p95": np.nan,
        }

    tr_offset_stats = {}
    if "tr_offset_est" in zone_ds:
        tr_off = zone_ds["tr_offset_est"].values.flatten()
        tr_off = tr_off[~np.isnan(tr_off)]
        tr_off = tr_off[tr_off > 0]
        if len(tr_off) > 0:
            tr_offset_stats = {
                "tr_offset_p5":  round(float(np.percentile(tr_off, 5)), 1),
                "tr_offset_p50": round(float(np.percentile(tr_off, 50)), 1),
                "tr_offset_p95": round(float(np.percentile(tr_off, 95)), 1),
            }

    stats = {
        "zone":      zone_name,
        "states":    box["states"],
        "n_samples": len(tdb),
        # Temperature
        "tdb_mean": round(float(np.mean(tdb)), 1),
        "tdb_std":  round(float(np.std(tdb)), 1),
        "tdb_p5":   round(float(np.percentile(tdb, 5)), 1),
        "tdb_p25":  round(float(np.percentile(tdb, 25)), 1),
        "tdb_p50":  round(float(np.percentile(tdb, 50)), 1),
        "tdb_p75":  round(float(np.percentile(tdb, 75)), 1),
        "tdb_p95":  round(float(np.percentile(tdb, 95)), 1),
        "tdb_max":  round(float(np.max(tdb)), 1),
        # Humidity
        "rh_mean": round(float(np.mean(rh)), 1),
        "rh_std":  round(float(np.std(rh)), 1),
        "rh_p5":   round(float(np.percentile(rh, 5)), 1),
        "rh_p50":  round(float(np.percentile(rh, 50)), 1),
        "rh_p95":  round(float(np.percentile(rh, 95)), 1),
        # Wind
        "wind_mean": round(float(np.mean(wind)), 2),
        "wind_p5":   round(float(np.percentile(wind, 5)), 2),
        "wind_p50":  round(float(np.percentile(wind, 50)), 2),
        "wind_p95":  round(float(np.percentile(wind, 95)), 2),
    }
    stats.update(tr_offset_stats)
    return stats


def plot_distributions(ds: xr.Dataset, output_path: str) -> None:
    """Plot temperature and humidity histograms for all zones."""
    fig, axes = plt.subplots(2, 5, figsize=(22, 8))
    fig.suptitle("ERA5 Climate Distributions — Indian Summer (Apr–Jun)",
                 fontsize=14, fontweight="bold")

    for col, (zone_name, box) in enumerate(ZONE_BOXES.items()):
        lat_min, lat_max = box["lat"]
        lon_min, lon_max = box["lon"]

        zone_ds = ds.sel(
            latitude=slice(lat_max, lat_min),
            longitude=slice(lon_min, lon_max),
        )

        tdb = zone_ds["t2m_c"].values.flatten()
        rh  = zone_ds["rh"].values.flatten()
        tdb = tdb[~np.isnan(tdb)]
        rh  = rh[~np.isnan(rh)]

        axes[0, col].hist(tdb, bins=50, color="tomato", alpha=0.7, edgecolor="white")
        axes[0, col].set_title(zone_name, fontweight="bold", fontsize=11)
        axes[0, col].set_xlabel("Temperature (°C)")
        p5, p95 = np.percentile(tdb, 5), np.percentile(tdb, 95)
        axes[0, col].axvline(p5,  color="blue", linestyle="--", linewidth=1.2, label=f"P5={p5:.0f}")
        axes[0, col].axvline(p95, color="red",  linestyle="--", linewidth=1.2, label=f"P95={p95:.0f}")
        axes[0, col].legend(fontsize=7)
        if col == 0:
            axes[0, col].set_ylabel("Frequency")

        axes[1, col].hist(rh, bins=50, color="steelblue", alpha=0.7, edgecolor="white")
        axes[1, col].set_xlabel("Relative Humidity (%)")
        p5r, p95r = np.percentile(rh, 5), np.percentile(rh, 95)
        axes[1, col].axvline(p5r,  color="blue", linestyle="--", linewidth=1.2, label=f"P5={p5r:.0f}")
        axes[1, col].axvline(p95r, color="red",  linestyle="--", linewidth=1.2, label=f"P95={p95r:.0f}")
        axes[1, col].legend(fontsize=7)
        if col == 0:
            axes[1, col].set_ylabel("Frequency")

    plt.tight_layout()
    plt.savefig(output_path, dpi=150)
    print(f"Saved: {output_path}")


def aggregate_climatology(by_year_df: pd.DataFrame, metric: str) -> pd.DataFrame:
    """Aggregate per-year zone stats to climatology using mean or median."""
    numeric_cols = [
        "n_samples",
        "tdb_mean", "tdb_std", "tdb_p5", "tdb_p25", "tdb_p50", "tdb_p75", "tdb_p95", "tdb_max",
        "rh_mean", "rh_std", "rh_p5", "rh_p50", "rh_p95",
        "wind_mean", "wind_p5", "wind_p50", "wind_p95",
        "tr_offset_p5", "tr_offset_p50", "tr_offset_p95",
    ]
    available_cols = [c for c in numeric_cols if c in by_year_df.columns]

    grouped = by_year_df.groupby(["zone", "states"], as_index=False)
    if metric == "mean":
        clim = grouped[available_cols].mean(numeric_only=True)
    else:
        clim = grouped[available_cols].median(numeric_only=True)

    n_years = grouped["source_year"].nunique().rename(columns={"source_year": "n_years"})
    clim = clim.merge(n_years, on=["zone", "states"], how="left")

    for col in clim.columns:
        if col in {"zone", "states"}:
            continue
        if col in {"n_samples", "n_years"}:
            clim[col] = clim[col].round(0).astype(int)
            continue
        if col.startswith("wind"):
            clim[col] = clim[col].round(2)
        else:
            clim[col] = clim[col].round(1)

    return clim


def print_suggested_config(stats_list: list, label: str):
    """Print suggested CLIMATE_ZONES config for generate_dataset.py."""
    print("\n" + "=" * 70)
    print(f"  SUGGESTED CLIMATE_ZONES UPDATE ({label})")
    print("=" * 70)

    for s in stats_list:
        # Use P5–P95 for generation ranges
        tr_lo = s.get("tr_offset_p5", 6.0)
        tr_hi = s.get("tr_offset_p95", 16.0)

        print(f"""
    "{s['zone']}": {{
        "tdb_range":       ({s['tdb_p5']}, {s['tdb_p95']}),
        "rh_range":        ({s['rh_p5']}, {s['rh_p95']}),
        "v_range":         ({s['wind_p5']}, {s['wind_p95']}),
        "tr_offset_range": ({tr_lo}, {tr_hi}),
        ...
    }},""")

    print("=" * 70)


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze ERA5 climate-zone statistics")
    parser.add_argument("--metric", choices=["median", "mean"], default="median")
    parser.add_argument("--yearly-dir", default=ERA5_YEARLY_DIR)
    parser.add_argument("--single-file", default=ERA5_ARCHIVE_PATH)
    args = parser.parse_args()

    try:
        input_files, mode = list_input_files(args.yearly_dir, args.single_file)
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}")
        sys.exit(1)

    print("\n" + "=" * 70)
    print("  ERA5 ZONE ANALYSIS")
    print("=" * 70)
    print(f"Mode   : {mode}")
    print(f"Files  : {len(input_files)}")
    print(f"Metric : {args.metric}")

    all_rows = []
    os.makedirs(ERA5_SUMMARY_DIR, exist_ok=True)
    os.makedirs(ERA5_PLOTS_DIR, exist_ok=True)

    for idx, src in enumerate(input_files, start=1):
        year = infer_year(src)
        title = f"Year {year}" if year > 0 else f"Source {idx}"
        print(f"\nProcessing {title}: {src}")

        allow_global_split = mode == "split"
        ds = load_and_prepare(src, allow_global_split=allow_global_split, verbose=(idx == 1))

        for zone_name, box in ZONE_BOXES.items():
            stats = extract_zone_stats(ds, zone_name, box)
            stats["source_year"] = year
            stats["source_file"] = os.path.basename(src)
            all_rows.append(stats)

        ds.close()

    by_year_df = pd.DataFrame(all_rows)
    by_year_path = os.path.join(ERA5_SUMMARY_DIR, "era5_zone_statistics_by_year.csv")
    by_year_df.to_csv(by_year_path, index=False)
    print(f"\nSaved: {by_year_path}")

    clim_df = aggregate_climatology(by_year_df, metric=args.metric)
    clim_path = os.path.join(ERA5_SUMMARY_DIR, "era5_zone_statistics_climatology.csv")
    compat_path = os.path.join(ERA5_SUMMARY_DIR, "era5_zone_statistics.csv")
    clim_df.to_csv(clim_path, index=False)
    clim_df.to_csv(compat_path, index=False)
    print(f"Saved: {clim_path}")
    print(f"Saved: {compat_path}")

    print("\nClimatology table:")
    print(clim_df.to_string(index=False))

    print_suggested_config(
        clim_df.to_dict(orient="records"),
        label=f"ERA5-grounded P5-P95 using {args.metric} of yearly zone stats",
    )

    latest_file = input_files[-1]
    print(f"\nGenerating latest-source distributions from: {latest_file}")
    ds_latest = load_and_prepare(
        latest_file,
        allow_global_split=(mode == "split"),
        verbose=False,
    )
    latest_plot_path = os.path.join(ERA5_PLOTS_DIR, "era5_zone_distributions_latest.png")
    plot_distributions(ds_latest, output_path=latest_plot_path)
    ds_latest.close()

    print(f"\n[DONE] Use {clim_path} to update climate ranges.")


if __name__ == "__main__":
    main()
