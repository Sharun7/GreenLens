"""

data_ingestion/management/commands/load_cbi_bonds.py



Django management command: load green bond data from the IMF/Refinitiv

green bond CSV (wide-format, one row per Country × Indicator, year columns).



Usage:

    python manage.py load_cbi_bonds --file=/path/to/green_bonds-21.csv

    python manage.py load_cbi_bonds --file=/path/to/green_bonds-21.csv --dry-run

    python manage.py load_cbi_bonds --file=/path/to/green_bonds-21.csv --latest-only

"""

import csv

import time

import traceback

from datetime import date

from pathlib import Path



from django.core.management.base import BaseCommand, CommandError

from geopy.exc import GeocoderTimedOut, GeocoderUnavailable

from geopy.geocoders import Nominatim



from data_ingestion.models import GreenBond



# -- IMF formal name -> geocodable name ----------------------------------------

COUNTRY_NAME_MAP = {

    "andorra, principality of":          "Andorra",

    "belarus, rep. of":                  "Belarus",

    "china, p.r.: hong kong":            "Hong Kong",

    "china, p.r.: macao":                "Macao",

    "china, p.r.: mainland":             "China",

    "cote d'ivoire":                     "Ivory Coast",

    "c\ufffd\ufffdote d'ivoire":          "Ivory Coast",

    "croatia, rep. of":                  "Croatia",

    "czech rep.":                        "Czech Republic",

    "dominican rep.":                    "Dominican Republic",

    "egypt, arab rep. of":               "Egypt",

    "estonia, rep. of":                  "Estonia",

    "fiji, rep. of":                     "Fiji",

    "jordan":                            "Jordan",

    "kazakhstan, rep. of":               "Kazakhstan",

    "korea, rep. of":                    "South Korea",

    "lao people's dem. rep.":            "Laos",

    "marshall islands, rep. of the":     "Marshall Islands",

    "netherlands, the":                  "Netherlands",

    "poland, rep. of":                   "Poland",

    "reunion":                           "Reunion",

    "r\ufffdunion":                       "Reunion",

    "r\ufffd\ufffdunion":                 "Reunion",

    "russian federation":                "Russia",

    "saudi arabia":                      "Saudi Arabia",

    "serbia, rep. of":                   "Serbia",

    "slovak rep.":                       "Slovakia",

    "slovenia, rep. of":                 "Slovenia",

    "taiwan province of china":          "Taiwan",

    "turkiye, rep. of":                  "Turkey",

    "t\ufffdrkiye, rep. of":             "Turkey",

    "t\ufffd\ufffdrkiye, rep. of":        "Turkey",

    "ukraine":                           "Ukraine",

    "united arab emirates":              "United Arab Emirates",

    "uzbekistan, rep. of":               "Uzbekistan",

    "venezuela, rep. bolivariana de":    "Venezuela",

    "world":                             "Washington DC",   # geocode placeholder for global aggregates

}



# -- Year columns present in the dataset ----------------------------------------

YEAR_COLS = [str(y) for y in range(2006, 2025)]



# -- Indicator filter: only load country-level issuance rows ------------------

# Each row with this indicator represents annual issuance for a country.

COUNTRY_INDICATORS = {

    "green bond issuances by country",

    "social bond issuances by country",

    "sustainability bond issuances by country",

    "sustainability linked bond issuances by country",

    # Also accept aggregate rows that lack "by country" suffix

    "green bond issuances",

    "social bond issuances",

    "sustainability bond issuances",

}



# -- Bond type -> project category ----------------------------------------------

BOND_TYPE_CATEGORY = {

    "green bond":         "other",

    "green bonds":        "other",

    "social bond":        "other",

    "sustainability bond": "other",

    "linked bond":        "other",

}



# -- Issuer type mapping -------------------------------------------------------

def _issuer_label(country: str, bond_type: str, issuer_type: str) -> str:

    it = (issuer_type or "").strip()

    if it and it.lower() not in ("not applicable", ""):

        return f"{country} - {it} ({bond_type})"

    return f"{country} - Sovereign/National ({bond_type})"





class Geocoder:

    """Nominatim geocoder with 1-req/sec rate limit and in-memory cache."""



    def __init__(self):

        self.geo = Nominatim(user_agent="greenlens-bond-loader/1.0", timeout=10)

        self._cache: dict[str, tuple[float, float] | None] = {}



    def geocode(self, country: str) -> tuple[float, float] | None:

        key = country.strip().lower()

        # Normalise IMF formal names to geocodable names

        query = COUNTRY_NAME_MAP.get(key, country.strip())

        cache_key = query.lower()

        if cache_key in self._cache:

            return self._cache[cache_key]

        try:

            time.sleep(1.1)

            result = self.geo.geocode(query, exactly_one=True)

            coords = (result.latitude, result.longitude) if result else None

        except (GeocoderTimedOut, GeocoderUnavailable):

            coords = None

        self._cache[cache_key] = coords

        return coords





class Command(BaseCommand):

    help = "Load IMF/Refinitiv green bond CSV (wide-format) into GreenBond model"



    def add_arguments(self, parser):

        parser.add_argument("--file", required=True, help="Path to green_bonds-21.csv")

        parser.add_argument(

            "--dry-run", action="store_true",

            help="Preview what would be loaded without saving",

        )

        parser.add_argument(

            "--latest-only", action="store_true",

            help="Only load the most recent year with data per country+bond_type (saves DB space)",

        )



    def handle(self, *args, **options):

        csv_path = Path(options["file"])

        if not csv_path.exists():

            raise CommandError(f"File not found: {csv_path}")



        dry_run = options["dry_run"]

        latest_only = options["latest_only"]

        geocoder = Geocoder()



        counts = {"created": 0, "updated": 0, "geocode_fail": 0,

                  "skipped": 0, "errors": 0}



        # -- Read CSV ----------------------------------------------------------

        with open(csv_path, encoding="utf-8-sig", errors="replace", newline="") as fh:

            reader = csv.DictReader(fh)

            rows = list(reader)



        self.stdout.write(f"Read {len(rows)} rows from {csv_path.name}")



        # -- Filter to country-level issuance rows -----------------------------

        country_rows = [

            r for r in rows

            if r.get("Indicator", "").strip().lower() in COUNTRY_INDICATORS

        ]

        self.stdout.write(f"Country-level issuance rows: {len(country_rows)}")



        # -- Build bond records ------------------------------------------------

        records: list[dict] = []

        for row in country_rows:

            country    = (row.get("Country") or "").strip()

            iso3       = (row.get("ISO3") or "").strip()

            bond_type  = (row.get("Bond_Type") or "Green Bond").strip()

            issuer_type = (row.get("Type_of_Issuer") or "").strip()

            currency   = (row.get("Principal_Currency") or "USD").strip()

            unit       = (row.get("Unit") or "").strip()   # "Billion US Dollars"



            if not country:

                counts["skipped"] += 1

                continue



            # Determine unit multiplier -> convert to USD millions

            unit_lower = unit.lower()

            if "billion" in unit_lower:

                multiplier = 1_000.0   # billion -> millions

            elif "million" in unit_lower:

                multiplier = 1.0

            else:

                multiplier = 1_000.0   # assume billions



            # Collect year values

            year_values = {}

            for y in YEAR_COLS:

                raw = (row.get(y) or "").strip()

                if raw and raw not in ("0", "0.0"):

                    try:

                        year_values[int(y)] = float(raw) * multiplier

                    except ValueError:

                        pass



            if not year_values:

                counts["skipped"] += 1

                continue



            if latest_only:

                latest_year = max(year_values)

                year_values = {latest_year: year_values[latest_year]}



            category = BOND_TYPE_CATEGORY.get(bond_type.lower(), "other")



            for year, amount_m in year_values.items():

                bond_id = f"{iso3 or country[:3].upper()}_{bond_type.replace(' ', '_')[:12]}_{year}"

                records.append({

                    "bond_id":          bond_id,

                    "country":          country,

                    "iso3":             iso3,

                    "bond_type":        bond_type,

                    "issuer_type":      issuer_type,

                    "category":         category,

                    "currency":         currency,

                    "amount_millions":  amount_m,

                    "year":             year,

                })



        self.stdout.write(f"Bond records to process: {len(records)}")

        self.stdout.write("Geocoding countries … (1 req/sec, cached per country)\n")



        # -- Geocode -----------------------------------------------------------

        for rec in records:

            coords = geocoder.geocode(rec["country"])

            rec["lat"] = coords[0] if coords else None

            rec["lon"] = coords[1] if coords else None

            if coords is None:

                counts["geocode_fail"] += 1



        # -- Save / preview ----------------------------------------------------

        for rec in records:

            try:

                if dry_run:

                    self.stdout.write(

                        f"  [DRY-RUN] {rec['bond_id']} | {rec['country']} | "

                        f"{rec['category']} | ${rec['amount_millions']:.1f}M | "

                        f"lat={rec['lat']} lon={rec['lon']}"

                    )

                    counts["created"] += 1

                    continue



                issuer = _issuer_label(rec["country"], rec["bond_type"], rec["issuer_type"])



                defaults = dict(

                    issuer_name=issuer[:255],

                    country=rec["country"][:100],

                    project_category=rec["category"],

                    project_description=(

                        f"{rec['bond_type']} issuances - {rec['country']} ({rec['year']})"

                    ),

                    amount_millions=rec["amount_millions"],

                    issuance_date=date(rec["year"], 1, 1),

                    bond_maturity_years=7,

                    lat=rec["lat"] if rec["lat"] is not None else 0.0,

                    lon=rec["lon"] if rec["lon"] is not None else 0.0,

                )



                obj, created = GreenBond.objects.update_or_create(

                    bond_id=rec["bond_id"],

                    defaults=defaults,

                )

                counts["created" if created else "updated"] += 1



            except Exception:

                counts["errors"] += 1

                self.stderr.write(f"  Error saving {rec.get('bond_id','?')}:")

                self.stderr.write(traceback.format_exc())



        # -- Summary -----------------------------------------------------------

        self.stdout.write("\n-- Summary ------------------------------")

        self.stdout.write(f"  Created        : {counts['created']}")

        self.stdout.write(f"  Updated        : {counts['updated']}")

        self.stdout.write(f"  Geocode fails  : {counts['geocode_fail']}")

        self.stdout.write(f"  Skipped        : {counts['skipped']}")

        self.stdout.write(f"  Errors         : {counts['errors']}")

        if dry_run:

            self.stdout.write("  (DRY-RUN -- nothing was saved)")

        self.stdout.write("-----------------------------------------\n")



