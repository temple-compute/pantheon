# Example data sources

All sequences are public NCBI GenBank records (influenza A, H1N1pdm09). No data
from any third-party pipeline repository is included.

| Sample   | Segment | Accession  | Strain | Note |
|----------|---------|------------|--------|------|
| Sample01 | HA | FJ966082 | A/California/04/2009 | unmodified |
| Sample01 | NA | FJ966084 | A/California/04/2009 | unmodified |
| Sample01 | MP | FJ966085 | A/California/04/2009 | unmodified (partial cds) |
| Sample01 | NS | FJ966086 | A/California/04/2009 | unmodified |
| Sample02 | HA | CY121680 | A/California/07/2009 | unmodified |
| Sample02 | NA | FJ984386 | A/California/07/2009 | unmodified |
| Sample03 | HA | FJ966082 | A/California/04/2009 | **derived QC fixture**: 120 nt replaced by `N` (fails `--max-n-frac`) |
| Sample03 | NA | FJ966084 | A/California/04/2009 | **derived QC fixture**: truncated to first 300 nt (fails length range) |
| Sample03 | (none) | FJ966085 | A/California/04/2009 | **deliberately malformed header** (no segment field) -> `errors.log` |

Sample names, years and countries in the headers are synthetic labels.
`metadata.csv` is entirely synthetic (fake dates/locations); columns follow the
common `ID,DATE,LOCATION,AGE GROUP,SEX,ORIGINATING LAB` layout.
