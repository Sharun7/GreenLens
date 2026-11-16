"""Official-resource directory and user-initiated, cached ASF metadata discovery."""

import csv
from datetime import date, timedelta

from django import forms
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import render

from data_ingestion.asf_search_client import search_sar_metadata
from greenwash_detector.live_connection import preview_path, read_connection_check


RESOURCE_GROUPS = [
    ("Data discovery and analysis", [
        ("NASA Earthdata Search", "https://search.earthdata.nasa.gov/search", "Earth science catalog"),
        ("ASF Vertex", "https://search.asf.alaska.edu/", "SAR catalog and processing services"),
        ("NASA Giovanni", "https://giovanni.gsfc.nasa.gov/", "Environmental time-series analysis"),
        ("NASA AppEEARS", "https://appeears.earthdatacloud.nasa.gov/", "Point and area sampling"),
        ("GES DISC Hydrology Time Series", "https://disc.gsfc.nasa.gov/information/tools?title=Hydrology%20Time%20Series", "Hydrological observations"),
        ("NOAA Climate Data Online", "https://www.ncei.noaa.gov/cdo-web/", "Weather and climate archives"),
        ("KNMI Climate Explorer", "https://climexp.knmi.nl/", "Climate series and statistical analysis"),
    ]),
    ("SAR methods and mission guides", [
        ("NISAR Data User Guide", "https://nisar-docs.asf.alaska.edu/", "Data products, access and limitations"),
        ("NASA SAR Fundamentals", "https://www.earthdata.nasa.gov/learn/earth-observation-data-basics/sar", "Radar geometry and scattering"),
        ("NASA Remote Sensing Basics", "https://www.earthdata.nasa.gov/learn/earth-observation-data-basics/remote-sensing", "Resolution and sensor characteristics"),
        ("NASA ARSET Training", "https://appliedsciences.nasa.gov/get-involved/training", "Remote sensing and disaster-management courses"),
        ("NISAR StoryMaps", "https://nisar.jpl.nasa.gov/applications/arcgis-storymaps/", "Flood, wildfire and deformation applications"),
        ("NISAR Applications Papers", "https://nisar.jpl.nasa.gov/applications/societal-benefit/", "Societal-benefit use cases"),
        ("UAVSAR Postcards", "https://uavsar.jpl.nasa.gov/education/postcards.html", "Interpreting radar composites"),
        ("NASA Time-Series Research", "https://ntrs.nasa.gov/citations/20090042747", "Chlorophyll time-series research and significance tests"),
    ]),
    ("Space agency partner resources", [
        ("CSA RADARSAT Constellation", "https://donnees-data.asc-csa.gc.ca/en/dataset/rcm", "RCM data access and restrictions"),
        ("CSA RADARSAT-1 Archive", "https://donnees-data.asc-csa.gc.ca/en/dataset/radarsat1", "Historical Canadian radar archive"),
        ("CSA SAR Tutorial", "https://github.com/asc-csa/Synthetic_Aperture_Radar_Tutorial", "Python and QGIS learning materials"),
        ("CONAE SAOCOM Catalog", "https://catalogos.conae.gov.ar/catalogo/catalogoSatSaocomInfo.html", "SAOCOM discovery and registration"),
        ("CONAE Registration Guidance", "https://www.argentina.gob.ar/noticias/la-informacion-saocom-cada-vez-mas-accesible", "SAOCOM account access"),
        ("GEO.ca", "https://geo.ca/", "Canadian geospatial information"),
        ("CSA SWOT Mission", "https://www.asc-csa.gc.ca/eng/satellites/swot/", "Surface-water elevation mission"),
        ("CSA Ecosystem Monitoring", "https://www.asc-csa.gc.ca/eng/satellites/everyday-lives/monitoring-and-protecting-our-ecosystems-from-space.asp", "Environmental monitoring applications"),
    ]),
]


class MetadataSearchForm(forms.Form):
    latitude = forms.FloatField(min_value=-90, max_value=90, initial=9.5)
    longitude = forms.FloatField(min_value=-180, max_value=180, initial=76.4)
    start = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    end = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs["class"] = "form-control"
        self.fields["latitude"].widget.attrs["step"] = "any"
        self.fields["longitude"].widget.attrs["step"] = "any"
        self.fields["start"].initial = date.today() - timedelta(days=365)
        self.fields["end"].initial = date.today()

    def clean(self):
        cleaned = super().clean()
        start, end = cleaned.get("start"), cleaned.get("end")
        if start and end and (start > end or (end - start).days > 3660):
            raise forms.ValidationError("Use an ordered date range of at most ten years.")
        return cleaned


def resources(request):
    form = MetadataSearchForm(request.GET if "search" in request.GET else None)
    result = None
    position = [9.5, 76.4]
    if form.is_bound and form.is_valid():
        data = form.cleaned_data
        position = [data["latitude"], data["longitude"]]
        result = search_sar_metadata(
            *position, data["start"].isoformat(), data["end"].isoformat(),
        )
        if request.GET.get("format") == "csv":
            response = HttpResponse(content_type="text/csv; charset=utf-8")
            response["Content-Disposition"] = 'attachment; filename="greenlens-asf-metadata.csv"'
            writer = csv.writer(response)
            writer.writerow(["dataset", "granule_id", "acquired_at", "browse_url", "catalog_url"])
            for granule in result["granules"]:
                writer.writerow([
                    ("'" + str(granule[key])) if str(granule[key]).startswith(("=", "+", "-", "@"))
                    else granule[key]
                    for key in ("dataset", "granule_id", "acquired_at", "browse_url", "catalog_url")
                ])
            return response
    export_query = request.GET.copy()
    export_query["format"] = "csv"
    return render(request, "dashboard/resources.html", {
        "form": form, "result": result, "resource_groups": RESOURCE_GROUPS,
        "map_position": position, "export_query": export_query.urlencode(),
        "gee_check": read_connection_check(),
    })


def gee_preview(request, period):
    path = preview_path(period)
    if path is None:
        raise Http404("No saved reference preview is available")
    response = FileResponse(path.open("rb"), content_type="image/png")
    response["Cache-Control"] = "private, max-age=60"
    return response