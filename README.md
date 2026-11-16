# 🌿 GreenLens

### Satellite-Verified Climate Risk Scoring for Green Bonds

[![License: BUSL-1.1](https://img.shields.io/badge/License-BUSL--1.1-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.11-green.svg)](https://python.org)
[![Django](https://img.shields.io/badge/Django-5.0-green.svg)](https://djangoproject.com)

GreenLens is an AI-powered climate intelligence platform that independently verifies green bond claims using satellite imagery, machine learning, and live financial data.

## 🔍 What It Does

- Computes Physical Climate Risk Scores (PCRS) for green-bond registry records
- Screens project claims with Google Earth Engine imagery when real satellite evidence is available
- Compares estimated yield spreads with model-implied spreads for pricing research
- Provides SHAP explanations for trained XGBoost predictions; bootstrap scores are demonstration estimates

## Project Verification

### PCRS Parameters And Feature Audit

`/about/#pcrs-model-parameters` is generated from the actual 20-input schema:
three hazard features, three extended country-context features, seven derived
features, and seven one-hot categories. Maturity and raw SPEI are transformed
inputs, not additional model columns. The section reports current source
availability and shows an actual saved input/SHAP snapshot when one exists.

`/api/pcrs/features/` returns the same catalog and coverage audit. Append
`?bond_id=YOUR_BOND_ID` to inspect that bond's saved inputs, source/fallback
status, coordinates, model fingerprint, raw score, SHAP baseline and clipping
adjustment. Older score rows retain an empty metadata object; no audit history
is fabricated for them.

Pipeline safeguards include real ISO3 resolution, country-specific extended
fallbacks, preserved recorded zeros, finite/domain validation, bounded drought
severity, and exact one-hot category encoding. Missing coordinates and invalid
maturity are not replaced by zero coordinates or a seven-year maturity.

Prepare Natural Earth's public 1:50m coastline archive once for geometry-based
200 km coastal features. The small archive is cached under `data/cache/`; it
is never downloaded during a page request. Without it, the explicitly labelled
legacy reference-point approximation remains available. The generalized map
is not a site boundary, floodplain, or guarantee of coastal protection. Docker
and the build script prepare the data before serving the app.

New training splits by country before preprocessing and fits the scaler on
training rows only. Country sample sizes need not be exactly 70/15/15. At least
20 rows and four country groups are required. Artifacts go to `models/pcrs_v2/`
as `model.pkl`, `scaler.pkl`, and `metadata.json`. The manifest records actual
hyperparameters, split countries, sample counts, source status, proxy-fit
metrics, mean held-out absolute SHAP values, and file checksums. The predictor
prefers a complete v2 manifest, rejects checksum/schema/preprocessing mismatches,
and identifies older artifacts as unverified legacy artifacts.

**Scientific boundary:** the target is still `100 * composite_hazard`, and that
composite is itself an input feature. A high proxy-fit R-squared is not evidence
that the model predicts real floods, losses, defaults, or independent effects
of carbon/governance/transition context. The embedded country tables and climate
ordinals are not verified live EDGAR, CAT, IEA, or CMIP6 feeds. This implementation
does not claim otherwise. Actual future validation needs sourced observations,
precise project locations, and independent outcome labels.

Windows PowerShell, from the updated project directory:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
$env:SECRET_KEY = "local-development-only"
.\.venv\Scripts\python.exe manage.py migrate --settings=greenlens.sqlite_settings
.\.venv\Scripts\python.exe manage.py prepare_pcrs_geography --settings=greenlens.sqlite_settings
.\.venv\Scripts\python.exe -m pytest tests/test_pcrs_model.py -q --ds=greenlens.sqlite_settings
```

For an explicitly labelled local research run on the current demo hazards:

```powershell
.\.venv\Scripts\python.exe manage.py train_pcrs_model --allow-demo --no-plot --settings=greenlens.sqlite_settings
.\.venv\Scripts\python.exe manage.py batch_score_bonds --only-missing --settings=greenlens.sqlite_settings
```

Omit `--allow-demo` when training on non-demo inputs. This is a guard against
known demo data, not certification of other inputs. Batch resume is per model
version, so bootstrap or older versions do not prevent new inference. New
scores preserve demo-input labels even when XGBoost computed them. Training
outputs and local databases are not automatically published to Railway; deploy
the complete audited artifact set and compatible database migration together.

### How It Works: Runtime Status

The four-step section on `/about/` now reports the current database state;
`/api/workflow/status/` exposes the same counts. It distinguishes stored
satellite observations from missing evidence and bootstrap estimates from
non-bootstrap scores. Counts use the latest record per bond.

The alert endpoint no longer invents random weather warnings or PCRS increases.
`/api/alerts/` returns only current saved pricing-review signals (explicitly
estimated) and satellite inconsistencies with genuine GEE provenance. No NOAA/IMD
weather forecast feed, email delivery, or automatic scheduler is claimed.

Optical thumbnail generation now evaluates the URL-producing call correctly;
missing land cover stays unknown rather than becoming a latitude-based guess.
GEE login is never launched interactively by this workflow. Configure authorized
GEE credentials separately: an Earthdata token does not grant GEE access.

Single-bond, API, and bulk pricing refreshes now share the supported estimator
and fitted pricing regression. A live risk-free benchmark does not turn an
estimated credit spread into an observed bond yield. Missing risk scores or an
unfitted regression produce an error rather than a fabricated prediction.

Repository review on 2026-11-15 found the main application modules implemented,
but the completion checklist should not be interpreted as independent validation
of the underlying financial or satellite results.

| Checklist Item | Verified Status And Limitation |
| --- | --- |
| 1,345 real green bonds | The bond fixture contains 1,345 records. The CSV importer expands country/year issuance aggregates, including several sustainable bond types, into registry records with country-level coordinates. These are not 1,345 independently identified bond issues or project sites. Production database counts were not queried. |
| PCRS: XGBoost + SHAP | Training, inference, explanation code, and model artifacts exist. Training targets are generated from a weighted hazard formula, not observed climate losses. Bootstrap scores and their contribution fields are not XGBoost predictions or genuine SHAP explanations. |
| GEE + ResNet-18; 156 flags | GEE/NDVI and CNN integrations exist. The checked-in greenwash fixture has 1,345 synthetic results, including 156 flags; these are not satellite detections. New checks without real imagery are now unverifiable, and the detector rejects synthetic CNN patches. |
| Pricing: 279 mispriced / 20% | Regression and gap analysis exist, but input spreads are estimated from rating tables and benchmark-rate adjustments rather than directly observed individual-bond yields. The stated count was not independently reproduced. The configured threshold is 1.3 standard deviations, so the percentage is not itself evidence of accuracy. |
| MLP climate predictions | A trainable MLP uses existing PCRS scores as targets. It is not independently validated against future climate observations or losses. |
| Regulatory scraping and reports | Scrapers and SEBI/ESMA report endpoints exist. Live scraping was not verified. Unsupported ESMA compliance fields now return null. Report availability is not regulatory certification; SEBI reviewer verification still requires independent evidence rather than disclosure-quality heuristics. |
| India climate module | All 36 state/union-territory profiles are configured. Static risk profiles are not equivalent to live IMD measurements. |
| Four SaaS tiers and limits | Tier models and middleware exist. Anonymous requests bypass subscription checks, and the default local-memory counters are process-local, so limits are not reliable across multiple workers. Billing/payment integration was not verified. |
| Monitoring | API health, drift, data-quality code, and Celery schedules exist. Background execution requires a configured broker, worker, and Beat scheduler; eager mode alone does not run scheduled jobs. |
| Dashboards, map, filters, CSV and Swagger | Views, routes, exports, and schema tooling exist, with regression tests for several pages. Viewport and hazard routes were repaired. A complete browser, filter, export, and schema-validation audit was not performed. Endpoint totals depend on router actions and format aliases; 22 application models were registered locally. |
| Gemini chat | Chat code and a route exist. The configured model and external API were not live-tested; a valid key and currently supported Gemini model are required. |
| Railway migration and deployment fixes | Deployment configuration and CPU-only PyTorch pins exist. Comma-separated allowed hosts and the build's CSV-loader arguments were repaired. The live Railway service, production import, and Render migration history were not verified. |

The build no longer imports the synthetic greenwash fixture. Existing database
rows are not automatically rewritten by these fixes: historical synthetic flags
must be identified by provenance and rechecked with real imagery before being
presented as satellite evidence. Country-level coordinates cannot establish
whether a particular financed project was constructed.

### Local Checks

Use Python 3.11 (the deployment version) or 3.12. The pinned scientific packages
do not support this container's default Python 3.14 environment.

```bash
python3.11 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
SECRET_KEY=local-test-only python manage.py check --settings=greenlens.sqlite_settings
SECRET_KEY=local-test-only pytest tests -q --ds=greenlens.sqlite_settings
```

These checks use an isolated SQLite test database and do not require production
credentials. They do not validate live GEE, Gemini, financial feeds, production
PostgreSQL behavior, or the scientific accuracy of the models. Set a separate,
secure secret key for deployment.

### NASA Earthdata Authentication

Set `EARTHDATA_TOKEN` in the process environment or private `.env` file. The
example file intentionally leaves it empty. Never commit a token, paste it into
logs, or put it in a command-line argument. Revoke and replace exposed tokens
through NASA Earthdata Login before using them.

`data_ingestion.earthdata_auth.earthdata_get()` sends the token as an
`Authorization: Bearer` header to HTTPS Earthdata/ASF hosts. It reads the
environment on every call, does not persist credentials, and refuses redirects
to avoid credential forwarding. Missing credentials, rejected/expired tokens
(HTTP 401), permission failures (HTTP 403), and network/server failures produce
safe `EarthdataError` messages without remote response bodies or request details.
Token expiry is determined by the server response, not unverified JWT claims.

The NASA CMR fetcher prefers this helper when `EARTHDATA_TOKEN` is set and
retains its legacy `NASA_TOKEN` / `NASA_USERNAME` / `NASA_PASSWORD` behavior
otherwise. Authentication failures are reported safely and return no granules;
existing hazard fallback estimates remain estimates, not observed measurements.
Earthdata credentials do not authenticate Google Earth Engine, which requires
its own credentials and project authorization.

```bash
SECRET_KEY=local-test-only pytest tests/test_earthdata_auth.py -q --ds=greenlens.sqlite_settings
```

These authentication tests mock all HTTP calls and require no real token.

### Configured GEE Processing Check

The noncommercial project `ee-auth-project-514903` was successfully checked on
2026-11-16 using read-only OAuth. No commercial registration or billing setting
was changed. Set `EE_PROJECT_ID` in your private environment; do not put OAuth
codes or tokens in source files or chat. Local OAuth credentials belong in the
Earth Engine CLI's standard private credential store, outside this repository.
Credentials saved in Codespaces do not automatically transfer to Railway or a
Windows checkout.

Run this explicitly from a configured Python 3.11/3.12 environment:

```bash
EE_PROJECT_ID=ee-auth-project-514903 SECRET_KEY=local-test-only python manage.py verify_gee_connection --settings=greenlens.sqlite_settings
```

It checks real GEE initialization, computes a reference NDVI/SAR comparison,
and caches two small Sentinel-2 PNG previews and a credential-free receipt under
ignored `data/cache/gee_connection/`. Signed thumbnail URLs are not stored in
the receipt or rendered in the page. `/resources/` serves only those cached
files; page loads do not invoke GEE. The reference location is not associated
with a bond, and the command never changes registry verification flags or PCRS.

Default comparisons use the last two completed years at 9.5 N, 76.4 E. NDVI
uses the existing 12-month anchor windows, optical previews use 180-day windows,
and SAR uses January-March. These different windows are labelled explicitly;
this is a functional connection check, not fused event evidence or a Kerala
flood backtest. A heuristic category conflict is displayed honestly, not treated
as proof of greenwashing. Raw SAR/NISAR products are not downloaded.

The first live run exposed and repaired two defects that mocks had missed:
GEE's decimal-formatted relative orbit keys (for example `165.0`) are now
normalized safely, and JRC's sparse water-product mask no longer removes valid
SAR land observations. The 90% SAR coverage requirement was not lowered.

### Sentinel-1 SAR Verifier

`greenwash_detector.sar_verifier.SarVerifier` is an offline/batch building block;
it is not called by dashboard requests and does not yet persist database results.
No additional dependency is required beyond the existing Earth Engine packages.
GEE must be authorized separately from NASA Earthdata. Use local
`earthengine authenticate`, the existing `EARTHENGINE_TOKEN` service-account
JSON environment variable, or `EE_SERVICE_ACCOUNT` plus `EE_PRIVATE_KEY_FILE`.
Set `EE_PROJECT_ID=drought-module2` unless another authorized project is intended.
Missing credentials return `unverifiable`; this module never starts interactive
authentication or substitutes synthetic observations.

```python
from greenwash_detector.sar_verifier import SarVerifier

with SarVerifier() as verifier:
		evidence = verifier.verify(
				lat=9.5,
				lon=76.4,
				before_start="2018-07-01",
				before_end="2018-08-01",
				after_start="2018-08-01",
				after_end="2018-09-01",
				claimed_category="water",
		)
print(evidence)
```

Run that code in a configured Django shell. Dates are ISO dates with exclusive
end dates. The example is a single-location query, not the district backtest or
a validated flood result.

Method:
- Query `COPERNICUS/S1_GRD`, IW mode, 10 m resolution, and both VV and VH within
	a 2 km radius. Compare medians from the same orbit pass and relative orbit.
	By default, each window must have at least two scenes. If several orbits qualify,
	select the one maximizing the smaller scene count, with orbit number as tie-breaker.
- Return spatial means of per-pixel median VV/VH backscatter in dB, their
	after-minus-before changes, and the spatial mean of the linear power ratio
	`10 ** ((VH_dB - VV_dB) / 10)`. Do not divide dB values to calculate a ratio.
- A candidate flooded pixel has VV change below `SAR_FLOOD_CHANGE_DB` (default
	-3 dB) and after-event VV below `SAR_FLOOD_MAX_AFTER_DB` (default -15 dB).
	Exclude permanent water (`waterClass=3`) using the latest JRC annual map from
	a calendar year before the comparison. No future-year water map is used.
	JRC's sparse water-product domain is not used as the SAR observation mask:
	it can omit valid land. SAR coverage is measured from both SAR bands and both
	periods. Only known permanent-water pixels are excluded; unmapped JRC pixels
	are not evidence that permanent water is absent. The separate water-map
	coverage diagnostic exposes this masking limitation.
- Sum pixel areas at `SAR_REDUCTION_SCALE_METRES` (default 20 m), then divide
	flooded area by the full geometric buffer area, including permanent water in
	the denominator. Also report observed coverage. If coverage is below
	`SAR_MIN_OBSERVED_FRACTION` (default 0.9), return no flooded fraction rather
	than interpreting missing pixels as dry. Small raster-boundary excesses in
	observed coverage are capped at one.
- Each REST computation has a 45-second request budget and one retry for
	client/server timeouts. This is not a 45-second budget for the complete job,
	which includes authentication, collection metadata, and image reduction.
	Sessions are closed by the context manager; create one verifier per batch worker.

The configurable `SAR_CATEGORY_THRESHOLDS` setting contains deliberately coarse,
unvalidated starting heuristics: VV minimum -18 dB for solar/wind screening;
VH minimum -18 dB and VH/VV ratio minimum 0.15 for reforestation screening;
VV maximum -15 dB and ratio maximum 0.3 for water screening. Environment-variable
counterparts are listed in `.env.example`. These values are not established
project signatures, and have not been fitted to Kerala or other validation data.

`verified` means observations pass that heuristic only; it does not verify that
a financed project exists. `inconsistent` identifies a threshold conflict, not
proven greenwashing. `unverifiable` includes missing observations, incompatible
orbits, insufficient coverage, missing permanent-water data, and processing errors.
Flood evidence and category consistency are separate outputs; passing a category
screen does not mean flood risk is low.

Limitations include country-level coordinates, coarse buffers, vegetation and
urban double-bounce, terrain shadow, incidence-angle differences, wet soils,
seasonal change, and median composites missing short-lived flood peaks. No terrain
or slope exclusion is applied here. Annual permanent-water maps end in 2021 and
can be stale for recent observations. Solar and wind installations cannot be
identified reliably from these buffer-level statistics. Independent flood maps,
accurate sites, and backtesting are still required; no accuracy claim is made.

```bash
SECRET_KEY=local-test-only pytest tests/test_sar_verifier.py -q --ds=greenlens.sqlite_settings
```

## 🛠️ Tech Stack

### Maps And Official Resource Discovery

The dashboard, location-verification view, and bond-site maps use Esri World
Imagery with attribution. The homepage defaults to satellite imagery and falls
back to OpenStreetMap when satellite tiles fail. Neither basemap requires an
Earthdata token or a client-side map API key in this configuration. These are
third-party basemaps, not NASA observations or dated evidence for a bond project;
provider terms, availability, and imagery age still apply.

The shared interface uses translucent glass surfaces with opaque fallbacks,
keyboard focus states, reduced-motion support, and a mobile map-first layout.
The active bond template now shows stored optical images when available and
explicit placeholders otherwise. Missing satellite evidence is not labelled as
a successful verification.

Visit `/resources/` for user-initiated ASF acquisition discovery, optional browse
previews, and CSV metadata export. The client queries `NISAR-SCIENCE-PRODUCTS`
(not the broader catalog that also includes ancillary weather files) and
Sentinel-1 at the requested coordinates. It returns at most six granules per
dataset, caches successful queries for 15 minutes and failures for one minute,
and uses bounded HTTP timeouts. It does not download or process raw SAR products.
No heavy GEE processing runs for this search.

Public catalog queries work without credentials. If `EARTHDATA_TOKEN` is set,
the ASF session sends it server-side only; it is not rendered into templates,
cached in results, or placed in browser URLs. Replace any exposed token before
configuring it. A search failure means coverage is unknown, not that no NISAR
observations exist. A granule footprint is not a project or flood verification.

The resource directory links to NASA Earthdata, ASF, NISAR guides, Giovanni,
AppEEARS, GES DISC hydrology, NOAA, ARSET, UAVSAR, KNMI, CSA, and CONAE. Those
external tools have distinct access workflows and data-use conditions; listing
them does not mean they are all integrated. NASA does not endorse GreenLens.

```bash
pip install -r requirements.txt
SECRET_KEY=local-test-only pytest tests/test_asf_search_client.py -q --ds=greenlens.sqlite_settings
```

Django 5 · PostgreSQL + PostGIS · XGBoost · PyTorch  
Google Earth Engine · World Bank API · Yahoo Finance · Leaflet.js

## ⚠️ License

This project is licensed under BUSL-1.1.  
Commercial use requires written permission from the author.  
Contact: sharuntomy7@gmail.com

## 👤 Author

**Sharun Tomy**  
MSc Data Analytics, Mahatma Gandhi University  
[LinkedIn](https://www.linkedin.com/in/sharun-tomy-5ba872271)

## ⚠️ Disclaimer

GreenLens is a research prototype.  
Not financial advice. Not a certified ESG rating.
