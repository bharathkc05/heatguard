"""
download_era5.py
================
Download ERA5 reanalysis data for India (Apr-Jun) as one file per year.

Default range is 2010 to the last complete year. This is safer and more
recoverable than a single giant multi-year request.

Requires CDS API credentials in ~/.cdsapirc:
    url: https://cds.climate.copernicus.eu/api
    key: f84d7fdb-2db8-49e0-82bd-cdaf62bb0f8e
"""

from datetime import datetime
import argparse
import os

import cdsapi

OUTPUT_DIR = os.path.join("era5_data", "yearly")


def build_years(start_year: int, end_year: int, include_current_year: bool) -> list:
    now_year = datetime.now().year
    max_year = now_year if include_current_year else now_year - 1
    final_end = min(end_year, max_year)
    if start_year > final_end:
        raise ValueError(f"Invalid range: start_year={start_year}, end_year={final_end}")
    return list(range(start_year, final_end + 1))


def download_one_year(client: cdsapi.Client, year: int, target_path: str) -> None:
    print(f"\n[DOWNLOAD] {year} -> {target_path}")
    client.retrieve(
        "reanalysis-era5-single-levels",
        {
            "product_type": "reanalysis",
            "variable": [
                "2m_temperature",
                "2m_dewpoint_temperature",
                "10m_u_component_of_wind",
                "10m_v_component_of_wind",
                "surface_solar_radiation_downwards",
            ],
            "year": [str(year)],
            "month": ["04", "05", "06"],
            "day": [f"{d:02d}" for d in range(1, 32)],
            # India working-window proxy in UTC
            "time": ["01:00", "04:00", "07:00", "10:00"],
            "area": [35, 68, 8, 97],
            "format": "netcdf",
        },
        target_path,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Download ERA5 summer data for India by year")
    parser.add_argument("--start-year", type=int, default=2010)
    parser.add_argument("--end-year", type=int, default=datetime.now().year)
    parser.add_argument(
        "--include-current-year",
        action="store_true",
        help="Include current year (may be incomplete depending on ERA5 availability)",
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip years that already have a downloaded file",
    )
    args = parser.parse_args()

    years = build_years(args.start_year, args.end_year, args.include_current_year)
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print("ERA5 India Summer download")
    print(f"  Years      : {years[0]}-{years[-1]} ({len(years)} years)")
    print(f"  Output dir : {OUTPUT_DIR}")

    client = cdsapi.Client()

    done = 0
    skipped = 0
    failed = 0

    for year in years:
        target_path = os.path.join(OUTPUT_DIR, f"era5_india_summer_{year}.nc")
        if args.skip_existing and os.path.exists(target_path):
            print(f"[SKIP] {year} (exists)")
            skipped += 1
            continue

        try:
            download_one_year(client, year, target_path)
            done += 1
        except Exception as exc:
            failed += 1
            print(f"[FAIL] {year}: {exc}")

    print("\nSummary")
    print(f"  Downloaded : {done}")
    print(f"  Skipped    : {skipped}")
    print(f"  Failed     : {failed}")


if __name__ == "__main__":
    main()
