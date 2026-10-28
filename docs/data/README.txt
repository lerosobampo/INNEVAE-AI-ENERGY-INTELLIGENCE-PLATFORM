INNEVA.E — Checkpoint 17.2D, timestamp-aligned datasets

All hourly tables span 2024-01-01 00:00 UTC through 2026-09-30 23:00 UTC.
The final hour ends at 2026-10-01 00:00 UTC.
The development samples are the last 90 days (2160 hours).

FIX:
KNMI HH=1 means the observation interval 00:00–01:00 UTC, so the
start timestamp is YYYYMMDD + (HH-1) hours. Weather has been REBUILT
from the original eight KNMI station archives, including the correct
last hour of September 30. Previous weather CSVs and the provisional
master used an incorrect one-hour alignment and should be replaced.

NO SHIFT for NED electricity demand/generation: explicit validfrom
and validto fields already specify the same hour. The extra preceding
December 31 row in yearly generation exports is excluded by the date
filter; shifting the entire series would corrupt the joins.

Prices retain their UTC source timestamp; source-specific market
publication timing still needs consideration for forecasting features.

Missing measurements are retained as null:
- offshore wind: 25 hours
- wholesale prices: 4 hours

National weather is an unweighted mean of the eight KNMI stations;
station reporting counts are retained. Missing observations are not
imputed. Original source files and SQLite database were not modified.

To reproduce:
python rebuild_aligned.py --knmi-dir /path/to/raw/knmi \
  --standardized-dir /path/to/previous/standardized_review \
  --output-dir /path/to/output
