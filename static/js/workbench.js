(() => {
    const form = document.getElementById('wb-filter-form');
    if (!form) return;
    const byId = (id) => document.getElementById(id);
    const state = {page: 1, pages: 1, total: 0, rows: [], mapItems: [], mode: 'globe', layer: 'risk', selected: null, timer: null, mapTimer: null, dataController: null, mapController: null, detailController: null};
    const scriptURL = document.currentScript?.src || `${location.origin}/static/js/workbench.js`;
    let globe = null, motionPaused = false;
    const status = byId('wb-map-message');
    const inspector = byId('wb-inspector');
    const content = byId('wb-inspector-content');
    const map = L.map('wb-map', {worldCopyJump: true, minZoom: 2, maxZoom: 18, zoomControl: false}).setView([20, 5], 2);
    L.control.zoom({position: 'bottomright'}).addTo(map);
    const imagery = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {attribution: 'Tiles &copy; Esri, Maxar, Earthstar Geographics, GIS User Community', maxNativeZoom: 18, maxZoom: 18});
    const streets = L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors', maxZoom: 19});
    let base = imagery;
    imagery.addTo(map);
    const markers = L.layerGroup().addTo(map);
    let tileErrors = 0;
    imagery.on('tileerror', () => {
        if (++tileErrors === 3 && base === imagery) {
            map.removeLayer(imagery); base = streets; streets.addTo(map);
            byId('wb-basemap').value = 'street'; byId('wb-source').textContent = 'OpenStreetMap';
            message('Satellite tiles unavailable. Street map shown instead.');
        }
    });
    streets.on('tileerror', () => { if (base === streets) message('Map tiles unavailable. Check your connection or use Table view.'); });

    function element(tag, text, className) {
        const node = document.createElement(tag);
        if (text !== undefined && text !== null) node.textContent = String(text);
        if (className) node.className = className;
        return node;
    }
    function message(text) { status.textContent = text; status.hidden = !text; }
    function params() {
        const data = new FormData(form);
        const query = new URLSearchParams();
        for (const [key, value] of data.entries()) if (String(value).trim()) query.set(key, String(value).trim());
        return query;
    }
    function format(value, digits = 1) { return value === null || value === undefined || !Number.isFinite(Number(value)) ? 'Unavailable' : Number(value).toFixed(digits); }
    function riskLabel(score) { return score === null || score === undefined ? 'Not scored' : score <= 33 ? 'Low' : score <= 66 ? 'Medium' : 'High'; }
    function riskClass(score) { return riskLabel(score).toLowerCase().replace(' ', '-'); }
    function markerColor(item) {
        if (state.layer === 'pricing') return item.mispriced ? '#e5a84d' : item.gap_bps === null || item.gap_bps === undefined ? '#8ba3a0' : '#62bfc7';
        return item.score === null || item.score === undefined ? '#91a5a1' : item.score <= 33 ? '#62ddb7' : item.score <= 66 ? '#e5a84d' : '#e65d68';
    }
    function renderChips() {
        const exportLink = document.querySelector('.wb-export');
        exportLink.search = params().toString();
        const host = byId('wb-filter-chips'); host.replaceChildren();
        const entries = [['q', 'Search'], ['country', 'Country'], ['category', 'Category'], ['year', 'From'], ['maturity', 'Maturity'], ['mispriced', 'Pricing gaps'], ['flagged', 'Satellite review']];
        for (const [name, label] of entries) {
            const input = form.elements[name];
            if (!input || !input.value || (input.type === 'checkbox' && !input.checked)) continue;
            const chip = element('button', `${label}${input.type === 'checkbox' ? '' : ': ' + input.value} ×`, 'wb-chip');
            chip.type = 'button'; chip.setAttribute('aria-label', `Remove ${label} filter`);
            chip.addEventListener('click', () => { if (input.type === 'checkbox') input.checked = false; else input.value = ''; updateFilters(); });
            host.append(chip);
        }
        const min = Number(form.elements.min_score.value), max = Number(form.elements.max_score.value);
        if (min > 0 || max < 100) {
            const chip = element('button', `PCRS ${min}–${max} ×`, 'wb-chip'); chip.type = 'button'; chip.setAttribute('aria-label', 'Remove PCRS range filter');
            chip.addEventListener('click', () => { form.elements.min_score.value = 0; form.elements.max_score.value = 100; updateFilters(); }); host.append(chip);
        }
    }
    async function loadData() {
        if (state.dataController) state.dataController.abort();
        state.dataController = new AbortController();
        const query = params(); query.set('page', state.page);
        byId('wb-freshness').textContent = 'Updating stored snapshot…';
        try {
            const response = await fetch(`/api/workbench/data/?${query}`, {signal: state.dataController.signal});
            if (!response.ok) throw new Error('Unable to load registry records.');
            const data = await response.json();
            state.rows = data.results; state.page = data.page; state.pages = data.pages; state.total = data.total;
            byId('wb-total').textContent = data.total.toLocaleString();
            byId('wb-freshness').textContent = data.freshness.latest_score_at ? `Scores updated ${new Date(data.freshness.latest_score_at).toISOString().slice(0, 10)} UTC` : 'No scores available';
            const suggestions = byId('wb-suggestions'); suggestions.replaceChildren();
            for (const row of data.results.slice(0, 10)) { const option = element('option'); option.value = row.bond_id; option.label = row.issuer; suggestions.append(option); }
            renderTable(data);
            if (state.mode === 'table') byId('wb-map-count').textContent = `${data.total.toLocaleString()} matching records`;
        } catch (error) {
            if (error.name === 'AbortError') return;
            byId('wb-freshness').textContent = 'Registry unavailable';
            byId('wb-table-body').replaceChildren();
            const row = document.createElement('tr'), cell = element('td', 'Unable to load records. Change a filter or retry.', 'wb-empty-cell'); cell.colSpan = 6; row.append(cell); byId('wb-table-body').append(row);
            message('Unable to load records. Check the connection and retry.');
        }
    }
    function renderTable(data) {
        const body = byId('wb-table-body'); body.replaceChildren();
        if (!data.results.length) { const row = document.createElement('tr'), cell = element('td', 'No records match these filters.', 'wb-empty-cell'); cell.colSpan = 6; row.append(cell); body.append(row); }
        for (const bond of data.results) {
            const row = document.createElement('tr'); row.tabIndex = 0; row.setAttribute('role', 'button'); row.setAttribute('aria-label', `Inspect ${bond.bond_id}`);
            const identity = document.createElement('td'); identity.append(element('strong', bond.issuer), element('small', bond.bond_id)); row.append(identity);
            row.append(element('td', bond.country), element('td', bond.category));
            const risk = document.createElement('td'); risk.append(element('span', `${format(bond.score)} · ${riskLabel(bond.score)}`, `wb-risk-badge ${riskClass(bond.score)}`)); row.append(risk);
            row.append(element('td', bond.gap_bps === null ? 'Unavailable' : `${format(bond.gap_bps)} bps · ${bond.pricing_status}`), element('td', bond.satellite_status));
            row.addEventListener('click', () => inspect(bond.bond_id)); row.addEventListener('keydown', event => {if (event.key === 'Enter' || event.key === ' ') {event.preventDefault(); inspect(bond.bond_id);}}); body.append(row);
        }
        byId('wb-page-label').textContent = `${data.total.toLocaleString()} matching · Page ${data.page} of ${data.pages}`;
        byId('wb-prev').disabled = data.page <= 1; byId('wb-next').disabled = data.page >= data.pages;
    }
    async function loadMap() {
        if (state.mapController) state.mapController.abort();
        state.mapController = new AbortController();
        const query = params(), bounds = map.getBounds(), west = bounds.getWest(), east = bounds.getEast();
        const normalize = value => ((value + 180) % 360 + 360) % 360 - 180;
        query.set('south', Math.max(-90, bounds.getSouth())); query.set('north', Math.min(90, bounds.getNorth()));
        query.set('west', east - west >= 360 ? -180 : normalize(west)); query.set('east', east - west >= 360 ? 180 : normalize(east)); query.set('zoom', map.getZoom());
        if (state.mode !== 'map') {query.set('south', -90); query.set('north', 90); query.set('west', -180); query.set('east', 180); query.set('zoom', 2);}
        byId('wb-map-count').textContent = 'Loading viewport…';
        try {
            const response = await fetch(`/api/workbench/map/?${query}`, {signal: state.mapController.signal});
            if (!response.ok) throw new Error('Map request failed');
            const data = await response.json(); state.mapItems = data.results; state.mapType = data.type;
            byId('wb-map-count').textContent = `${data.total.toLocaleString()} ${state.mode === 'map' ? 'in view' : 'global records'}${data.truncated ? ' · Zoom in for more' : ''}`;
            updateGlobe(data);
            document.querySelector('.wb-legend strong').textContent = data.type === 'clusters' ? 'MEAN CLUSTER PCRS' : 'RISK SCORE';
            renderMarkers();
            if (data.truncated) message('Some map results are not shown. Zoom in or use the paginated table.');
            else if (!data.results.length) message('No records in this map area. Move the map or clear filters.');
            else message('');
        } catch (error) { if (error.name !== 'AbortError') {byId('wb-map-count').textContent = 'Map data unavailable'; message('Map data could not load. Move the map or change a filter to retry.');} }
    }
    function renderMarkers() {
        markers.clearLayers();
        for (const item of state.mapItems) {
            if (!Number.isFinite(Number(item.lat)) || !Number.isFinite(Number(item.lon))) continue;
            if (state.mapType === 'clusters') {
                const size = item.count > 99 ? 40 : item.count > 9 ? 34 : 28;
                const icon = L.divIcon({className:'wb-cluster-wrap',html:`<span class="wb-cluster" style="width:${size}px;height:${size}px">${Number(item.count)}</span>`,iconSize:[size,size]});
                const marker = L.marker([item.lat,item.lon], {icon, title:`${item.count} records; zoom in`, keyboard:true});
                marker.on('click', () => map.setView([item.lat,item.lon], Math.min(8, map.getZoom() + 2))); markers.addLayer(marker);
            } else {
                const selected = state.selected === item.bond_id;
                const marker = L.circleMarker([item.lat,item.lon], {radius:selected ? 9 : 6, color:selected ? '#fff' : '#d8f8ec', weight:selected ? 3 : 1.5, fillColor:markerColor(item), fillOpacity:.9, keyboard:true});
                marker.bindTooltip(`${item.bond_id} · ${riskLabel(item.score)} PCRS`, {direction:'top'});
                marker.on('click', () => inspect(item.bond_id)); markers.addLayer(marker);
            }
        }
    }
    function updateGlobe(data) {
        if (!globe) return;
        globe.setData(data);
        if (state.mode === 'globe' && (form.elements.country.value || form.elements.q.value) && data.results.length) {
            globe.focus(Number(data.results[0].lat), Number(data.results[0].lon));
        }
    }
    function addField(parent, label, value, extra) {
        const row = element('div', null, 'wb-detail-row'); row.append(element('dt', label)); const detail = element('dd', value || 'Unavailable'); if (extra) detail.append(element('small', extra)); row.append(detail); parent.append(row);
    }
    async function inspect(bondId) {
        state.selected = bondId; renderMarkers(); inspector.classList.add('open');
        content.replaceChildren(element('div', 'Loading asset intelligence…', 'wb-inspector-loading'));
        if (state.detailController) state.detailController.abort(); state.detailController = new AbortController();
        try {
            const response = await fetch(`/api/workbench/bonds/${encodeURIComponent(bondId)}/`, {signal:state.detailController.signal});
            if (!response.ok) throw new Error('detail failed');
            const data = await response.json(); content.replaceChildren();
            const header = element('div', null, 'wb-inspector-header'); header.append(element('span', 'REGISTRY RECORD', 'wb-mini-label'), element('h3', data.issuer), element('p', data.bond_id, 'wb-technical'));
            const location = element('p', `${data.country} · ${data.location_confidence || 'unknown'} location`, 'wb-inspector-location'); header.append(location); content.append(header);
            const score = element('div', null, 'wb-score-block'); const number = element('strong', format(data.score)); score.append(number); const summary = element('div'); summary.append(element('span', 'PHYSICAL CLIMATE RISK', 'wb-mini-label'), element('p', `${riskLabel(data.score)} risk · ${data.score_input_status}`)); score.append(summary); content.append(score);
            const identity = element('dl', null, 'wb-details'); addField(identity, 'Category', data.category); addField(identity, 'Issued', data.issuance_date); addField(identity, 'Maturity', `${data.maturity} years`); addField(identity, 'Registry source', data.registry_source || 'Not documented'); content.append(identity);
            content.append(element('div', 'HAZARD INPUTS', 'wb-section-label'));
            const hazards = element('dl', null, 'wb-details');
            if (data.hazards) {addField(hazards, 'Flood', format(data.hazards.flood, 3));addField(hazards, 'Heat', format(data.hazards.heat, 3));addField(hazards, 'Drought SPEI', format(data.hazards.drought_spei, 3));addField(hazards, 'Input source', data.hazards.source, `${data.hazards.status} · ${data.hazards.date}`);} else addField(hazards, 'Hazard data', 'Unavailable');
            content.append(hazards, element('div', 'EVIDENCE & PRICING', 'wb-section-label'));
            const evidence = element('dl', null, 'wb-details'); addField(evidence, 'Satellite', data.satellite_status, data.satellite?.reason || 'A screening result is not proof of project completion.'); addField(evidence, 'Pricing gap', data.pricing ? `${format(data.pricing.gap)} bps` : 'Unavailable', data.pricing ? `${data.pricing_status} · ${data.pricing.source}` : ''); addField(evidence, 'Model', data.score_version || 'Unavailable', data.score_driver?.label || 'No explanation available'); content.append(evidence);
            if (data.shap_factors.length) {
                content.append(element('div', 'SAVED MODEL CONTRIBUTIONS', 'wb-section-label'));
                const factors = element('dl', null, 'wb-details');
                for (const factor of data.shap_factors) addField(factors, factor.feature.replaceAll('_', ' '), `${Number(factor.contribution) >= 0 ? '+' : ''}${format(factor.contribution, 3)}`);
                content.append(factors, element('p', 'SHAP explains this model output; it does not validate real-world loss prediction.', 'wb-inspector-note'));
            }
            const link = element('a', null, 'wb-detail-link'); link.href = `/bond/${encodeURIComponent(data.bond_id)}/`; link.append(document.createTextNode('Open full bond profile ')); const arrow = element('i', null, 'bi bi-arrow-up-right'); arrow.setAttribute('aria-hidden','true'); link.append(arrow); content.append(link);
        } catch (error) {if (error.name !== 'AbortError') {content.replaceChildren(element('div', 'Asset details could not be loaded. Select the record again to retry.', 'wb-inspector-loading'));}}
    }
    function updateFilters() {
        const min = form.elements.min_score, max = form.elements.max_score;
        if (Number(min.value) > Number(max.value)) max.value = min.value;
        byId('wb-range-label').textContent = `${min.value} - ${max.value}`;
        state.page = 1; renderChips(); loadData(); loadMap();
    }
    function setView(mode) {
        state.mode = mode;
        document.querySelector('.orbital-stage').dataset.view = mode;
        for (const candidate of ['globe', 'map', 'table']) {
            byId(`wb-${candidate}-panel`).hidden = candidate !== mode;
            byId(`wb-${candidate}-tab`).classList.toggle('active', candidate === mode);
            byId(`wb-${candidate}-tab`).setAttribute('aria-pressed', String(candidate === mode));
        }
        byId('wb-basemap').hidden = mode !== 'map';
        byId('wb-source').textContent = mode === 'globe' ? 'Earth imagery: Three.js examples' : base === imagery ? 'Esri World Imagery' : 'OpenStreetMap';
        if (mode === 'map') requestAnimationFrame(() => {map.invalidateSize(); loadMap();});
        else if (mode === 'globe') loadMap();
        else byId('wb-map-count').textContent = `${state.total.toLocaleString()} matching records`;
    }
    async function startGlobe() {
        const fail = () => {
            byId('wb-globe-tab').disabled = true;
            byId('wb-globe-tab').title = '3D rendering unavailable; Map and Table remain accessible';
            byId('wb-globe-panel').dataset.globeStatus = 'unavailable';
            globe?.dispose(); globe = null;
            setView('map'); message('3D rendering is unavailable in this browser. The interactive map and table remain available.');
        };
        try {
            const module = await import(new URL('./orbital-globe.js?v=2', scriptURL).href);
            globe = await module.createOrbitalGlobe(byId('wb-globe-panel'), {onSelect(item) {
                if (item.bond_id) inspect(item.bond_id);
                else {setView('map'); map.setView([item.lat, item.lon], 8);}
            }, onFailure: fail});
            globe.setLayer(state.layer);
            updateGlobe({results: state.mapItems});
            byId('wb-globe-loading').hidden = true;
            for (const id of ['wb-globe-motion', 'wb-globe-reset', 'wb-globe-in', 'wb-globe-out']) byId(id).disabled = false;
            byId('wb-globe-reset').addEventListener('click', () => globe.reset());
            byId('wb-globe-in').addEventListener('click', () => globe.zoom(1));
            byId('wb-globe-out').addEventListener('click', () => globe.zoom(-1));
            byId('wb-globe-motion').addEventListener('click', event => {
                motionPaused = !motionPaused; globe.setPaused(motionPaused);
                event.currentTarget.setAttribute('aria-pressed', String(motionPaused));
                event.currentTarget.setAttribute('aria-label', motionPaused ? 'Resume globe rotation' : 'Pause globe rotation');
                event.currentTarget.title = motionPaused ? 'Resume globe rotation' : 'Pause globe rotation';
                event.currentTarget.querySelector('i').className = motionPaused ? 'bi bi-play-fill' : 'bi bi-pause-fill';
            });
            const motion = matchMedia('(prefers-reduced-motion: reduce)');
            const syncMotionButton = () => {byId('wb-globe-motion').disabled = motion.matches; byId('wb-globe-motion').title = motion.matches ? 'Rotation disabled by reduced-motion preference' : 'Pause or resume rotation';};
            syncMotionButton(); motion.addEventListener('change', syncMotionButton);
            window.addEventListener('pagehide', event => {if (!event.persisted) globe?.dispose();});
        } catch (error) {fail();}
    }
    form.addEventListener('submit', event => { event.preventDefault(); clearTimeout(state.timer); updateFilters(); });
    form.addEventListener('change', updateFilters);
    byId('wb-search').addEventListener('input', () => {clearTimeout(state.timer); state.timer = setTimeout(updateFilters, 350);});
    byId('wb-min').addEventListener('input', () => {clearTimeout(state.timer); state.timer = setTimeout(updateFilters, 250);});
    byId('wb-max').addEventListener('input', () => {clearTimeout(state.timer); state.timer = setTimeout(updateFilters, 250);});
    byId('wb-reset').addEventListener('click', () => {form.reset(); byId('wb-search').value = ''; document.querySelectorAll('[data-quick]').forEach(button => button.classList.toggle('active', button.dataset.quick === 'all')); updateFilters();});
    document.querySelectorAll('[data-quick]').forEach(button => button.addEventListener('click', () => {form.elements.mispriced.checked = button.dataset.quick === 'mispriced'; form.elements.flagged.checked = button.dataset.quick === 'flagged'; document.querySelectorAll('[data-quick]').forEach(item => item.classList.toggle('active', item === button)); updateFilters();}));
    byId('wb-prev').addEventListener('click', () => {if (state.page > 1) {state.page--; loadData();}});
    byId('wb-next').addEventListener('click', () => {if (state.page < state.pages) {state.page++; loadData();}});
    for (const mode of ['globe','map','table']) byId(`wb-${mode}-tab`).addEventListener('click', () => setView(mode));
    byId('wb-layer').addEventListener('change', event => {state.layer=event.target.value; renderMarkers(); globe?.setLayer(state.layer); document.querySelector('.wb-legend').hidden=state.layer==='pricing'; message(state.layer==='pricing' ? 'Amber indicates a stored pricing-gap flag; cyan is unflagged. Inputs may be estimates.' : '');});
    byId('wb-basemap').addEventListener('change', event => {map.removeLayer(base); base=event.target.value==='street'?streets:imagery; base.addTo(map); byId('wb-source').textContent=base===imagery?'Esri World Imagery':'OpenStreetMap'; tileErrors=0; message('');});
    byId('wb-filter-toggle').addEventListener('click', event => {const open=byId('wb-filters').classList.toggle('open');event.currentTarget.setAttribute('aria-expanded',String(open));});
    byId('wb-mobile-inspector').addEventListener('click', () => inspector.classList.add('open'));
    byId('wb-close-inspector').addEventListener('click', () => inspector.classList.remove('open'));
    document.addEventListener('keydown', event => {if(event.key==='Escape') inspector.classList.remove('open');});
    map.on('moveend', () => {if (state.mode === 'map') {clearTimeout(state.mapTimer); state.mapTimer=setTimeout(loadMap,250);}});
    byId('wb-basemap').hidden = true;
    renderChips(); loadData(); loadMap(); startGlobe();
})();