# 🌍 GreenLens: Satellite-Verified Climate Risk Scoring System

**A geospatial Machine Learning platform that brings empirical transparency to the global Green Bond market by verifying "green" claims using satellite imagery and quantifying unpriced climate risks.**

[![Live Demo](https://img.shields.io/badge/Demo-Live_Deployment-success?style=for-the-badge)](https://greenlens-demo.example.com)

![GreenLens Dashboard Screenshot](https://via.placeholder.com/1200x600.png?text=GreenLens+Dashboard+Screenshot)

## 📖 Problem Statement

The $3 Trillion Green Bond market suffers from an "information asymmetry" problem where ESG scores rely heavily on self-reported corporate disclosures, creating a ripe environment for **greenwashing**. Furthermore, the physical climate risks (e.g., severe droughts, floods, extreme heat) that threaten the long-term viability of the underlying green infrastructure are rarely priced into the bond's yield spread accurately. **GreenLens solves this by relying exclusively on physics, geospatial satellite pixels, and objective machine learning models.**

## ⚙️ How It Works

* **Geospatial Processing:** Geocodes bonds globally and tracks the exact 5km radius of the funded infrastructure project.
* **Physical Climate Risk Scoring (PCRS):** An XGBoost model calculates a proprietary 1-100 risk score using high-resolution drought, flood, and heat data.
* **Satellite Greenwash Verification:** Uses Google Earth Engine (Sentintel-2) and a CNN to compare pre- and post-project vegetation indexes (NDVI), flagging bonds where satellite reality contradicts the issuer's claims (e.g., claimed "reforestation" showing vegetation loss).
* **Pricing Gap Analysis:** Compares the actual market yield spread with the ML-predicted "fair value" spread to identify mispriced greeniums.

## 🛠️ Tech Stack

![Python](https://img.shields.io/badge/Python-3.11-3776AB?style=flat-square&logo=python&logoColor=white)
![Django](https://img.shields.io/badge/Django-5.0-092E20?style=flat-square&logo=django&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL_PostGIS-316192?style=flat-square&logo=postgresql&logoColor=white)
![XGBoost](https://img.shields.io/badge/XGBoost-Models-orange?style=flat-square)
![Leaflet.js](https://img.shields.io/badge/Leaflet-Maps-199900?style=flat-square&logo=leaflet&logoColor=white)
![Google Earth Engine](https://img.shields.io/badge/Google_Earth_Engine-Satellite-4285F4?style=flat-square&logo=google&logoColor=white)

## 🚀 Installation & Setup

1. **Clone the repository:**
   ```bash
   git clone https://github.com/yourusername/greenlens.git
   cd greenlens
   ```

2. **Set up the virtual environment:**
   ```bash
   python -m venv venv
   source venv/bin/activate  # Or `venv\Scripts\activate` on Windows
   pip install -r requirements.txt
   ```

3. **Configure the Database & Environment:**
   - Install PostgreSQL 14+ and the PostGIS extension.
   - Copy `.env.example` to `.env` and fill in your DB credentials and `EE_SERVICE_ACCOUNT`.

4. **Run Migrations and Server:**
   ```bash
   python manage.py migrate
   python manage.py runserver
   ```

## 🔌 API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/bonds/` | GET | List and filter all geocoded green bonds. |
| `/api/bonds/{id}/` | GET | Retrieve detailed metadata for a specific bond. |
| `/api/risk/scores/` | GET | Retrieve all PCRS computations. |
| `/api/pricing/gaps/` | GET | Retrieve spread mismatch predictions. |
| `/api/greenwash/flags/`| GET | List satellite-verified greenwash consistency flags. |
| `/api/docs/` | GET | Interactive Swagger UI API documentation. |

## 📊 Data Sources

* **Sovereign Bond Frameworks:** Climate Bonds Initiative (CBI), IMF, Refinitiv.
* **Climate Hazard Data:** World Bank Climate Change Knowledge Portal (CCKP).
* **Satellite Imagery:** Google Earth Engine (Copernicus Sentinel-2 SR Harmonized).
## 🌍 Sustainable Development Goals (SDG) Alignment

GreenLens actively supports the UN SDGs by bringing transparency to climate finance:
* **SDG 13 (Climate Action):** Quantifying physical climate risks to infrastructure.
* **SDG 7 (Affordable and Clean Energy):** Verifying the deployment of renewable energy plants.
* **SDG 17 (Partnerships for the Goals):** Bridging data gaps between institutional investment and earth observation sciences.

---
**Author:** Sharun Tomy, MSc Data Analytics, Mahatma Gandhi University
