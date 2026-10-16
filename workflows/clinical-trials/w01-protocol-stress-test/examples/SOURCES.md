# Example data sources

## `protocol/NCT03036150.json`

- **What:** the full ClinicalTrials.gov record for NCT03036150, "A Study to Evaluate the Effect of Dapagliflozin on Renal Outcomes and Cardiovascular Mortality in Patients With Chronic Kidney Disease" (Dapa-CKD). The record lists AstraZeneca as lead sponsor, with no collaborators.
- **Source:** ClinicalTrials.gov API v2, `https://clinicaltrials.gov/api/v2/studies/NCT03036150`, retrieved 2026-10-16. The record's last update was posted 2021-07-07. The response was saved unmodified apart from pretty-printing.
- **Terms:** ClinicalTrials.gov is a service of the U.S. National Library of Medicine (NLM). Its records are public-domain U.S. government data. Cite ClinicalTrials.gov and the NCT ID when reusing them. Neither NLM nor the sponsor endorses this workflow. See <https://clinicaltrials.gov/about-site/terms-conditions>.
- **Not fetched at runtime:** the workflow reads only this committed snapshot.

## `criteria.reviewed.json`

- **What:** the human-reviewed computable rule set: feature definitions with SNOMED CT, LOINC and RxNorm codes, the prescreen and one rule per eligibility criterion.
- **Source:** written by hand for this workflow from the eligibility text above. Codes were checked against the Synthea v4.0.0 module definitions and a generated sample. It is an interpretation for simulation, not the sponsor's operational definition.

## Synthetic population (generated at runtime, not committed)

- **Tool:** Synthea v4.0.0 (`synthea-with-dependencies.jar`, SHA-256 `ed43c20ad40ba5c3bc724503a5af032715fe3c491620b766148e7c2361e6ecc1`). Downloaded from <https://github.com/synthetichealth/synthea/releases/tag/v4.0.0> on first use.
- **License:** Apache License 2.0.
- **Content:** entirely synthetic patients. They contain no real patient data.
