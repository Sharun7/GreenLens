(() => {
    const node = document.getElementById('pilot-data');
    if (!node) return;
    const data = JSON.parse(node.textContent);
    const map = L.map('pilot-map', {scrollWheelZoom: false, zoomAnimation: false, fadeAnimation: false}).setView([31, -100], 6);
    L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {attribution: 'Tiles &copy; Esri; boundaries USGS/LBNL', maxZoom: 18}).addTo(map);
    const layers = new Map();
    function field(parent, label, value) {
        const row = document.createElement('div');
        const title = document.createElement('dt'); title.textContent = label;
        const detail = document.createElement('dd'); detail.textContent = value ?? 'Unavailable';
        row.append(title, detail); parent.append(row);
    }
    function fixed(value, digits = 3) {return typeof value === 'number' && Number.isFinite(value) ? value.toFixed(digits) : 'Unavailable';}
    function select(projectId, zoom = true) {
        const project = data.projects.find(item => item.id === projectId);
        if (!project) return;
        document.getElementById('pilot-name').textContent = project.name;
        const detail = document.getElementById('pilot-detail'); detail.replaceChildren();
        const identity = document.createElement('dl');
        field(identity, 'Source project / county', `${project.source_id} / ${project.county}`);
        field(identity, 'Boundary review', project.review);
        field(identity, 'Source release', project.version);
        field(identity, 'Boundary SHA-256', project.boundary_sha256);
        field(identity, 'Source capacity (AC)', project.capacity_mw === null ? 'Unavailable' : `${project.capacity_mw} MW`);
        field(identity, 'Evidence status', project.status);
        field(identity, 'Collected UTC', project.collected_at);
        detail.append(identity);
        const optical = project.optical, sar = project.sar;
        const measurements = document.createElement('dl');
        field(measurements, 'Baseline window [start, end)', project.windows.before_start ? `${project.windows.before_start} / ${project.windows.before_end}` : null);
        field(measurements, 'Comparison window [start, end)', project.windows.after_start ? `${project.windows.after_start} / ${project.windows.after_end}` : null);
        field(measurements, 'S2 baseline / comparison NDVI', `${fixed(optical.before?.ndvi)} / ${fixed(optical.after?.ndvi)}`);
        field(measurements, 'S2 baseline / comparison coverage', `${fixed(optical.before?.observed_fraction)} / ${fixed(optical.after?.observed_fraction)}`);
        field(measurements, 'Optical quality', optical.reason);
        field(measurements, 'SAR VV change', sar.sar_change_db === null || sar.sar_change_db === undefined ? 'Unavailable' : `${fixed(sar.sar_change_db)} dB`);
        field(measurements, 'SAR relative orbit / coverage', `${sar.relative_orbit ?? 'Unavailable'} / ${fixed(sar.observed_fraction)}`);
        field(measurements, 'SAR quality / heuristic limitations', sar.reason);
        detail.append(measurements);
        document.querySelectorAll('[data-project]').forEach(button => button.setAttribute('aria-pressed', String(Number(button.dataset.project) === projectId)));
        layers.forEach((layer, identifier) => layer.setStyle({color: identifier === projectId ? '#ffffff' : '#62ddb7', weight: identifier === projectId ? 3 : 1.5}));
        if (zoom && layers.has(projectId)) map.fitBounds(layers.get(projectId).getBounds(), {maxZoom: 15, padding: [30, 30], animate: false});
        const source = document.getElementById('pilot-review-source');
        if (source) {source.value = project.source_id; document.getElementById('pilot-review-hash').value = project.boundary_sha256; document.getElementById('pilot-review-notes').value = '';}
    }
    const polygons = L.geoJSON(data.geojson, {style: {color: '#62ddb7', weight: 1.5, fillOpacity: .3}, onEachFeature(feature, layer) {
        layers.set(feature.properties.id, layer);
        const label = document.createElement('span'); label.textContent = feature.properties.name;
        layer.bindTooltip(label); layer.on('click', () => select(feature.properties.id));
    }}).addTo(map);
    if (data.geojson.features.length) map.fitBounds(polygons.getBounds(), {padding: [20, 20]});
    document.querySelectorAll('[data-project]').forEach(button => button.addEventListener('click', () => select(Number(button.dataset.project))));
    const wanted = new URLSearchParams(location.search).get('project');
    const initial = data.projects.find(project => project.source_id === wanted) || data.projects[0];
    if (initial) select(initial.id, Boolean(wanted));
})();