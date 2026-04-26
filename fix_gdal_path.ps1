# fix_gdal_path.ps1
# Run this ONCE to copy GDAL/GEOS DLLs from AppData (blocked by Application Control)
# to C:\ProgramData\greenlens-gdal\ (trusted system path).
#
# Usage:  .\fix_gdal_path.ps1
# No admin rights needed (ProgramData is writable by standard users).

$Source = "C:\Users\sharu\AppData\Local\Programs\OSGeo4W\bin"
$Dest   = "C:\ProgramData\greenlens-gdal"

# If not found in default AppData, try alternative OSGeo4W locations
$altSources = @(
    "C:\OSGeo4W\bin",
    "C:\Program Files\OSGeo4W\bin"
)
foreach ($alt in $altSources) {
    if (-not (Test-Path $Source) -and (Test-Path $alt)) {
        $Source = $alt
    }
}

if (-not (Test-Path $Source)) {
    Write-Error "OSGeo4W bin not found. Please run osgeo4w-setup.exe first."
    exit 1
}

Write-Host "Source : $Source"
Write-Host "Dest   : $Dest"

New-Item -ItemType Directory -Force -Path $Dest | Out-Null

# Copy all DLLs (GDAL + all its dependencies)
$dlls = Get-ChildItem -Path $Source -Filter "*.dll" -File
$total = $dlls.Count
$i = 0
foreach ($dll in $dlls) {
    $i++
    Write-Progress -Activity "Copying GDAL DLLs" -Status "$($dll.Name)" -PercentComplete (($i / $total) * 100)
    Copy-Item -Path $dll.FullName -Destination $Dest -Force
}

# Verify GDAL and GEOS are present
$gdal = Get-ChildItem -Path $Dest -Filter "gdal*.dll" | Select-Object -First 1
$geos = Join-Path $Dest "geos_c.dll"

Write-Host ""
if ($gdal) {
    Write-Host "GDAL DLL : $($gdal.FullName)" -ForegroundColor Green
} else {
    Write-Warning "GDAL DLL not found in $Dest"
}

if (Test-Path $geos) {
    Write-Host "GEOS DLL : $geos" -ForegroundColor Green
} else {
    Write-Warning "geos_c.dll not found in $Dest"
}

Write-Host ""
Write-Host "Done. DLLs copied to $Dest" -ForegroundColor Cyan
Write-Host "Now run: python manage.py makemigrations pricing_analysis" -ForegroundColor Yellow
Write-Host "         python manage.py migrate" -ForegroundColor Yellow
Write-Host "         python manage.py train_pcrs_model" -ForegroundColor Yellow
