# Project Evidence Pilot

## Current Implementation

The pilot is separate from the aggregate-derived bond registry. Open `/pilot/`
or `/api/pilot/status/` to inspect current readiness. Nothing in this implementation
turns a solar facility into a verified green-bond-financed project.

The initial local cohort contains 30 ground-mounted solar facilities in Texas,
covering 25 counties, from the official USGS/LBNL USPVDB v4.0 release
`uspvdb_v4_0_20260414.geojson`. Source mapping confidence is 4. These are
aerial-image-mapped array polygons, not field verification by GreenLens.

Source: https://energy.usgs.gov/uspvdb/data/

Citation: https://doi.org/10.5066/P9IA3TUS

Live collection on 16 November 2026 produced:

| Measurement | Projects |
| --- | --- |
| Cloud-screened Sentinel-2 polygon measurements | 30 |
| Sentinel-2 plus quality-gated Sentinel-1 measurements | 15 |
| Optical-only; insufficient matching SAR acquisitions | 15 |
| Analyst-approved boundaries | 0 |
| Independently reviewed damage outcomes | 0 |

Measurements compare June-August 2024 with June-August 2025. This is a retrospective
evidence comparison, not a future-risk forecast or a damage-labeling procedure.

The XGBoost evaluation, encoder-artifact comparison, climate-period comparison and
CVXPY optimizer have automated tests. Actual model validation and optimizer use
remain blocked by missing independently reviewed labels and financial inputs.
No ResNet/Prithvi/SatMAE production comparison or genuine loss-backtest result is
claimed. Synthetic examples exist only inside isolated unit tests.

## Reproduce the Cohort

Install the project dependencies, configure a local secret through the environment,
and use the existing SQLite development settings where appropriate:

```bash
python manage.py migrate --settings=greenlens.sqlite_settings
python manage.py import_project_pilot --state TX --limit 30 --settings=greenlens.sqlite_settings
python manage.py collect_project_pilot --limit 30 --settings=greenlens.sqlite_settings
```

Earth Engine must already be authorized outside the web request. No interactive
authentication is started by collection. No keys or authorization codes belong
in source control or chat. The currently authorized project is noncommercial;
commercial data use requires a separate terms and licensing review.

The importer uses a fixed seed over sorted eligible official source IDs. Repeat
imports retain existing cohort members even when a release adds facilities.
Changed boundaries, removed facilities or reduced source quality require review;
they are not silently substituted. Downloads are bounded, archive checksums and
source metadata are retained, and ingestion runs record completion/failure status.
These are monitored command runs, not proof that an always-on scheduler is running.

The collector stores the boundary hash, recipe version, explicit date windows,
cloud-screened optical coverage, counts, NDVI/NDMI, terrain measurements and SAR
orbit/coverage metadata. Windows must be ordered, nonoverlapping and season-matched.
SCL cloud screening and polygon pixel coverage are checked; missing data stays
missing. SAR compares a shared relative orbit and pass. Its category/flood screen
is heuristic, not independently calibrated classification.

There is no automatic bond linkage, greenwashing verdict, outcome creation,
customer subscription activation or promotion of a new production model.

## Analyst Boundary Review

1. Sign in with an account having staff status and permission to change pilot projects.
2. Inspect the source release, polygon, selected facility and dated evidence in `/pilot/`.
3. Approve or reject the boundary with substantive evidence notes. The operation
   records the reviewer and timestamp and rejects a stale polygon hash.
4. Review ambiguous facilities and source changes separately; do not treat source
   mapping confidence as operational verification or proof of financed-project identity.

Admin records are available under Pilot Projects, Pilot Outcomes, Pilot Evidence
and Pilot Ingestion Runs. Evidence and ingestion logs are read-only in admin.
No analyst approval was fabricated by the coding assistant.

## Independent Outcome Contract

Create real outcome records through the staff admin workflow only after sourcing
independent evidence. Approval of a boundary does not approve an outcome.

Each outcome requires:

- A reviewed project polygon and an explicitly identified event/outcome date.
- A directly observed damage fraction in [0, 1], evidence URL, method and notes.
- A label-availability date no earlier than the outcome date.
- A reviewer and review timestamp for independently observed labels.
- A feature date strictly before the outcome.
- Exactly the seven baseline measurements listed below, each with finite values,
  a measured-data provenance kind, an HTTPS source URL and `available_on` date
  no later than the feature date.

| Feature | Meaning |
| --- | --- |
| s2_ndvi | Pre-outcome polygon vegetation index |
| s2_ndmi | Pre-outcome polygon moisture index |
| s1_vv_db | Pre-outcome VV backscatter in dB |
| s1_vh_db | Pre-outcome VH backscatter in dB |
| elevation_m | Source-documented terrain elevation |
| slope_deg | Source-documented terrain slope |
| capacity_mw | Capacity known at the prediction date, not a later revised value |

In `feature_provenance`, each feature key maps to an object with `kind`
(`observed` or `official_measurement`), `source_url`, and ISO `available_on`.
`features` maps the same seven keys to measured numbers. Independently observed
outcomes fail approval if the measurement schema or chronology is invalid.

Do not use NDVI changes, model scores, simulated losses or an issuer's unsupported
claim as ground-truth damage. Include undamaged and ambiguous cases rather than
selecting only known disasters. For historical replay, independently confirm that
the boundary, source releases, capacity and measurements were knowable at the
prediction date; later digitization or surviving-asset selection can introduce bias.
The software validates declared provenance but cannot establish that declarations
or human labels are truthful.

The initial evaluator requires one outcome per project. Repeated projects are
rejected to prevent train/test leakage. Multi-event evaluation needs a separate
grouped and temporally embargoed protocol rather than reusing this first-pilot split.

## XGBoost and Evaluated Intervals

```bash
python manage.py evaluate_project_pilot \
  --train-before 2022-01-01 \
  --calibrate-before 2024-01-01 \
  --held-out-counties Ector \
  --alpha 0.1 \
  --settings=greenlens.sqlite_settings
```

Those dates are illustrative protocol parameters, not a claim that historical
labels have been obtained. Choose cutoffs and held-out counties before examining
test outcomes, with sufficient independently labeled projects in every partition.
The real current cohort correctly refuses this command because it has no labels.

Training projects precede the first cutoff and their labels must already have
been available. Calibration projects fall between cutoffs with labels available
before testing. Later projects in non-held-out counties form a temporal test;
later projects in held-out counties form a geographic test. No project appears
in more than one partition. Ineligible chronological rows are reported as excluded.

The fixed XGBoost baseline is compared with a training-mean baseline. Calibration
uses absolute residuals and the finite-sample order statistic
`ceil((n_calibration + 1) * (1 - alpha))`. An insufficient calibration sample is
rejected; test labels never supply the conformal radius. Coverage, width, MAE and
RMSE are evaluated on each untouched test set and coverage is broken down by county.
Small county samples are explicitly marked insufficient for regional assurance.

Exchangeability is not guaranteed across geography or time. Nominal conformal
coverage is not a guarantee under distribution shift. This is a damage-fraction
baseline, not a validated bond-default or financial-return model.

Evaluation artifacts go under ignored `data/cache/project_pilot/<dataset-hash>/`.
They do not overwrite `models/pcrs_v2/`. The existing production proxy baseline
remains labeled as a proxy until a reviewed promotion process is justified.

## Encoder Benchmark

`benchmark_project_encoders` evaluates supplied prediction artifacts; it does not
download checkpoints or execute/fine-tune foundation encoders automatically.

```bash
python manage.py benchmark_project_encoders \
  --evaluation path/to/evaluation.json \
  --predictions path/to/encoder_predictions.json \
  --settings=greenlens.sqlite_settings
```

The prediction file is a list containing a `resnet18` baseline and at least one
`prithvi` or `satmae` bundle. Each bundle requires checkpoint and preprocessing
SHA-256 values, checkpoint/license URLs, input bands, a head-training recipe,
`training_project_ids` equal to the frozen training IDs and a `predictions` object
mapping exactly the frozen test IDs to finite predicted damage fractions.

The label/feature fingerprint must match the evaluated dataset. Different test
projects, changed labels, unknown checkpoint provenance or training on test IDs
are rejected. Reported MAE/RMSE concern the supplied encoder-plus-head predictions,
not generic model capability. Reproducing training and reviewing spectral-band,
normalization, resolution and licensing compatibility remain mandatory.

## Scenario and Optimization Gates

`risk_scoring.pilot_scenarios.compare_climate_periods` accepts reviewed period
averages with source, dataset, model, downscaling, bias correction and resolution
metadata. It requires matched historical/future periods and at least three models
for both `tasmax` and `pr` under a supported SSP scenario. Kelvin/Celsius and
precipitation flux/mm-per-day conversions are explicit. Model spread is not called
a confidence interval, and no arbitrary financial-loss multiplier is produced.
No real projection ensemble has been loaded yet.

`pricing_analysis.pilot_optimization.optimize_reviewed_portfolio` uses CVXPY and
CLARABEL for historical-scenario CVaR minimization. It requires at least 60 aligned
return scenarios, unique instruments, source/usage-rights/reviewer metadata,
frequency and known-as-of dates. It enforces full investment, long-only weights,
allocation caps and an optional same-frequency historical-mean return constraint.
Solver output is checked; infeasible cases do not become partial portfolios.

Estimated spreads and undocumented inputs are blocked. Historical return summaries
are not future-return forecasts. Liquidity, transaction costs, mandates and future
distribution shift are not fully modeled. No actual financial portfolio was
optimized because no defensible market-return dataset was supplied.

## Research-User Study

This implementation does not claim a completed human trial. Recruit consenting
research/advisory participants and use a written protocol:

1. Have two analysts independently review the same frozen cases, including negative
   and ambiguous examples, without seeing model scores during label creation.
2. Record evidence completeness, disagreements and adjudication decisions.
3. Compare a manual workflow with the evidence workspace in randomized order.
4. Measure time per review, missing evidence found, reviewer agreement and supported
   versus unsupported flags. Do not claim investment alpha from task completion.
5. Obtain permission before storing any private documents. Do not put participant
   identities, customer holdings or licensed raw data in the repository.

## Before Commercial Use

Still required after the research pilot: independent outcomes and real held-out
results, actual encoder artifacts, reviewed climate/market inputs, real user
feedback, organization-owned private datasets and cross-tenant tests, shared-cache
quotas, monitored worker/scheduler deployment, backup restoration, security review
and commercial data/model licensing review. Existing session-scoped portfolios
and staff-only shared writes are not a complete multi-tenant commercial platform.

The pilot page makes unmet data gates explicit. No billing, subscription activation,
paid Earth Engine configuration or outreach to third parties was performed.