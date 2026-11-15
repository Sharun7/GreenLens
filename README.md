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
