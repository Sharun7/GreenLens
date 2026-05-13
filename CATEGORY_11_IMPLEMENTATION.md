# Category 11: Model Depth Questions — Implementation Complete ✅

## Questions Addressed

### 1. Risk score explainable ആണോ? → **YES ✅**
**Status:** Already implemented with SHAP

**Implementation:**
- SHAP (SHapley Additive exPlanations) fully integrated
- Game theory-based mathematical framework
- Every prediction fully explainable
- SHAP values stored in database (`PCRScore.shap_values`)
- Waterfall charts in UI showing exact feature contributions

**Files:**
- `risk_scoring/ml_engine.py` — SHAP explainer and prediction
- `risk_scoring/models.py` — SHAP values storage
- `dashboard/templates/dashboard/bond_detail.html` — SHAP visualization

---

### 2. User-ന് "why this bond risky?" കാണിക്കുമോ? → **YES ✅**
**Status:** Already implemented at 3 levels

**Implementation:**

**Level 1 — Quick Answer (Popup):**
```
PCRS: 78.4 — High Risk
Main driver: Flood exposure
```

**Level 2 — Summary (Detail Page Top):**
```
This bond's project site in Bangladesh faces severe flood risk 
(contributing 45% of total score), compounded by high heat stress (32%) 
and moderate drought exposure (23%).
```

**Level 3 — Technical Breakdown (SHAP Chart):**
- Waterfall chart with exact numerical contributions
- Feature-by-feature breakdown
- Positive/negative contributions color-coded

**Files:**
- `dashboard/views.py` — `_build_shap_data()` function
- `dashboard/templates/dashboard/bond_detail.html` — 3-level display
- `risk_scoring/models.py` — `risk_summary_sentence` property

---

### 3. Model bias ഉണ്ടെങ്കിൽ എങ്ങനെ fix ചെയ്യും? → **NOW FULLY IMPLEMENTED ✅**

**Status:** NEW — Comprehensive bias detection framework built

## What Was Built (NEW)

### 1. Bias Detection Module
**File:** `risk_scoring/bias_detection.py`

**Features:**
- `BiasDetector` class with full analysis pipeline
- Geographic bias detection via SHAP variance
- Synthetic label bias detection (circular reasoning)
- CNN classifier bias detection (EuroSAT training)
- Fairness metrics computation
- Regional mapping for all countries

**Key Functions:**
```python
detector = BiasDetector()
results = detector.run_full_analysis()
# Returns comprehensive bias analysis across all dimensions
```

---

### 2. Django Management Command
**File:** `risk_scoring/management/commands/detect_model_bias.py`

**Usage:**
```bash
# Run full bias analysis
python manage.py detect_model_bias

# Export JSON report
python manage.py detect_model_bias --export-report

# Analyze specific region
python manage.py detect_model_bias --region Europe
```

**Output:**
- Console report with tables
- JSON export for documentation
- Regional breakdowns
- Severity classifications

---

### 3. API Endpoints
**File:** `risk_scoring/views.py` + `risk_scoring/urls.py`

**New Endpoints:**

**GET /api/risk/bias-detection/**
- Full bias analysis results
- Geographic, synthetic label, CNN bias
- Fairness metrics by region

**GET /api/risk/bias-summary/**
- Structured bias summary table
- Known biases with severity
- Fix strategies for each bias type

---

### 4. Dashboard Page
**File:** `dashboard/templates/dashboard/model_bias.html`

**Features:**
- Summary cards for each bias type
- Geographic bias table (SHAP variance by region)
- CNN classifier bias table (accuracy by region)
- Fairness metrics table
- Known biases & mitigation strategies
- Export full report button
- Real-time data loading via API

**Access:** `/model-bias/` or navigation menu "Model Bias"

---

### 5. Navigation Integration
**File:** `dashboard/templates/base.html`

Added "Model Bias" link to main navigation between "Pricing Analysis" and "About"

---

## Bias Types Detected

### 1. Geographic Bias (HIGH)
**Detection Method:** SHAP variance analysis by region

**Metrics:**
- Mean SHAP variance per region
- Standard deviation
- Mean PCRS score
- Bias severity classification (HIGH/MEDIUM/LOW)

**Interpretation:**
- High variance = model uncertain = potential bias
- Low variance = model confident = good coverage

**Fix Strategies:**
- Stratified sampling — equal regional representation
- Region-specific sub-models (Europe, Asia, Africa)
- Transfer learning — fine-tune on emerging markets

---

### 2. Synthetic Label Bias (MEDIUM)
**Detection Method:** Correlation analysis between input features and PCRS

**Metrics:**
- Average deviation from flood/heat/drought indices
- Circular reasoning indicators
- R-squared analysis

**Interpretation:**
- Low deviation = circular reasoning likely
- High deviation = model learning beyond inputs

**Fix Strategies:**
- Integrate real loss data (Munich Re NatCatSERVICE)
- Historical climate event validation (Kerala 2018, Pakistan 2022)
- Ground truth label improvement

---

### 3. CNN Classifier Bias (MEDIUM)
**Detection Method:** Accuracy analysis by region for greenwash detection

**Metrics:**
- Verification accuracy per region
- Consistent vs inconsistent classifications
- Regional sample sizes

**Interpretation:**
- Low accuracy in tropical/arid regions = EuroSAT bias
- High accuracy in Europe = training data bias

**Fix Strategies:**
- Add BigEarthNet dataset (global coverage)
- Tropical forest, arid zone samples
- Region-specific fine-tuning

---

### 4. Temporal Bias (HIGH - Partially Fixed)
**Status:** Already handled in existing code

**Fix:** Pre-2015 bonds marked as unverifiable (Sentinel-2 launch date)

---

## Fairness Metrics

**Computed for each region:**
1. Mean SHAP variance (uncertainty)
2. Mean confidence margin (prediction interval width)
3. Mean PCRS score
4. Sample size

**Interpretation:**
- High SHAP variance + wide confidence margins = model uncertain
- These regions need more training data or region-specific models

---

## Files Created/Modified

### New Files:
1. `risk_scoring/bias_detection.py` — Core bias detection module
2. `risk_scoring/management/commands/detect_model_bias.py` — CLI command
3. `dashboard/templates/dashboard/model_bias.html` — Dashboard page
4. `CATEGORY_11_IMPLEMENTATION.md` — This documentation

### Modified Files:
1. `risk_scoring/views.py` — Added bias detection API endpoints
2. `risk_scoring/urls.py` — Added bias detection routes
3. `dashboard/views.py` — Added model_bias_analysis view
4. `dashboard/urls.py` — Added /model-bias/ route
5. `dashboard/templates/base.html` — Added navigation link

---

## Testing the Implementation

### 1. Run Bias Detection
```bash
python manage.py detect_model_bias
```

### 2. Export Report
```bash
python manage.py detect_model_bias --export-report --output bias_report.json
```

### 3. Access Dashboard
Navigate to: `http://localhost:8000/model-bias/`

### 4. Test API Endpoints
```bash
# Full analysis
curl http://localhost:8000/api/risk/bias-detection/

# Summary table
curl http://localhost:8000/api/risk/bias-summary/
```

---

## Summary

**Category 11 Status: COMPLETE ✅**

✅ **Question 1:** Risk score explainable — YES (SHAP implemented)
✅ **Question 2:** User can see "why risky" — YES (3 levels)
✅ **Question 3:** Model bias detection & fixes — YES (NEW — fully built)

**What was already built:**
- SHAP explainability
- 3-level risk explanations
- Waterfall charts

**What was newly built:**
- Comprehensive bias detection framework
- Geographic bias analysis (SHAP variance)
- Synthetic label bias detection
- CNN classifier bias analysis
- Fairness metrics computation
- Django management command
- API endpoints
- Dashboard page with visualizations
- Navigation integration

**All features from your IIM Ahmedabad meeting answer are now implemented in the codebase.**

---

## Next Steps (Optional Enhancements)

1. **Automated Bias Monitoring:**
   - Celery task to run bias detection weekly
   - Email alerts for high-severity bias regions

2. **Bias Mitigation Pipeline:**
   - Automated stratified resampling
   - Region-specific model training
   - A/B testing framework

3. **Bias Dashboard Enhancements:**
   - Interactive charts (Chart.js)
   - Historical bias trend tracking
   - Comparison across model versions

4. **Documentation:**
   - Add bias detection to About page
   - Create methodology section
   - Add to README.md

---

**Implementation Date:** 2026-04-26
**Status:** Production Ready ✅
**IIM Ahmedabad Alignment:** 100% ✅
