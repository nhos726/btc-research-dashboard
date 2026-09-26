# Point-in-time data

This directory is written by GitHub Actions, not by the Streamlit process.

- `latest_snapshot.json` — newest collected snapshot.
- `history/YYYY/MM/DD/HH.json` — one UTC snapshot per hour.

`observed_at` is the collection time. `source_times` keeps the source timestamps
reported by each collector when available. Missing observations remain `null` and
source failures are recorded in `errors`; gaps are not estimated.

The public raw URL for the latest snapshot is:

`https://raw.githubusercontent.com/nhos726/btc-research-dashboard/snapshots/data/latest_snapshot.json`
