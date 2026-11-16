import * as THREE from 'three';
import {OrbitControls} from '../vendor/three/OrbitControls.js';

const ASSETS = new URL('../vendor/three/', import.meta.url);
const RADIUS = 1.8;

function positionAt(latitude, longitude, radius = RADIUS) {
    const polar = THREE.MathUtils.degToRad(90 - latitude);
    const azimuth = THREE.MathUtils.degToRad(longitude + 180);
    return new THREE.Vector3(-radius * Math.sin(polar) * Math.cos(azimuth), radius * Math.cos(polar), radius * Math.sin(polar) * Math.sin(azimuth));
}

function pointColor(item, layer) {
    if (layer === 'pricing') return item.mispriced ? '#efc17e' : item.gap_bps === undefined || item.gap_bps === null ? '#b7c5cb' : '#a7dce6';
    return item.score === null || item.score === undefined ? '#c1ced1' : item.score <= 33 ? '#bcf2a0' : item.score <= 66 ? '#f4c785' : '#f38b88';
}

export async function createOrbitalGlobe(host, {onSelect, onFailure} = {}) {
    const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)');
    const renderer = new THREE.WebGLRenderer({alpha: true, antialias: true, powerPreference: 'low-power', preserveDrawingBuffer: true});
    renderer.setPixelRatio(Math.min(devicePixelRatio || 1, innerWidth < 768 ? 1.5 : 2));
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.13;
    const canvas = renderer.domElement;
    canvas.className = 'orbital-canvas';
    canvas.tabIndex = 0;
    canvas.setAttribute('role', 'img');
    canvas.setAttribute('aria-label', 'Interactive Earth showing stored registry locations; equivalent records are available in Table view');
    host.prepend(canvas);

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(42, 1, .1, 60);
    camera.position.copy(positionAt(20, 20).normalize().multiplyScalar(6.1));
    const controls = new OrbitControls(camera, canvas);
    controls.enablePan = false;
    controls.enableZoom = false;
    controls.enableDamping = !reducedMotion.matches;
    controls.dampingFactor = .065;
    controls.autoRotateSpeed = .38;
    controls.minPolarAngle = .16;
    controls.maxPolarAngle = Math.PI - .16;
    controls.autoRotate = !reducedMotion.matches;
    const originalPosition = camera.position.clone();

    scene.add(new THREE.HemisphereLight('#edf5ff', '#4f615d', 2.25));
    const sunlight = new THREE.DirectionalLight('#fff0d5', 2.5);
    sunlight.position.set(5, 4, -4);
    scene.add(sunlight);
    const rimLight = new THREE.DirectionalLight('#9dcada', 1.5);
    rimLight.position.set(-4, 0, 3);
    scene.add(rimLight);

    const textureLoader = new THREE.TextureLoader();
    let textures;
    try {
        textures = await Promise.all(['earth-day.jpg', 'earth-normal.jpg', 'earth-specular.jpg'].map(name => textureLoader.loadAsync(new URL(name, ASSETS).href)));
    } catch (error) {
        controls.dispose(); renderer.dispose(); canvas.remove();
        throw new Error('Earth imagery could not be loaded.');
    }
    textures[0].colorSpace = THREE.SRGBColorSpace;
    textures.forEach(texture => {texture.anisotropy = Math.min(4, renderer.capabilities.getMaxAnisotropy());});
    const earth = new THREE.Mesh(new THREE.SphereGeometry(RADIUS, 80, 56), new THREE.MeshPhongMaterial({
        map: textures[0], normalMap: textures[1], normalScale: new THREE.Vector2(.38, .38),
        specularMap: textures[2], specular: new THREE.Color('#718c94'), shininess: 12,
    }));
    scene.add(earth);

    const atmosphere = new THREE.Mesh(new THREE.SphereGeometry(RADIUS * 1.025, 64, 48), new THREE.ShaderMaterial({
        uniforms: {rimColor: {value: new THREE.Color('#73bed4')}}, transparent: true, depthWrite: false,
        side: THREE.BackSide, blending: THREE.AdditiveBlending,
        vertexShader: `varying vec3 surfaceNormal; varying vec3 viewDirection;
            void main() { vec4 worldPosition = modelMatrix * vec4(position, 1.0);
                surfaceNormal = normalize(mat3(modelMatrix) * normal);
                viewDirection = normalize(cameraPosition - worldPosition.xyz);
                gl_Position = projectionMatrix * viewMatrix * worldPosition; }`,
        fragmentShader: `uniform vec3 rimColor; varying vec3 surfaceNormal; varying vec3 viewDirection;
            void main() { float edge = pow(1.0 - abs(dot(normalize(surfaceNormal), normalize(viewDirection))), 3.2);
                gl_FragColor = vec4(rimColor, edge * 0.48); }`,
    }));
    scene.add(atmosphere);

    const referenceMaterial = new THREE.LineBasicMaterial({color: '#9bd4d2', transparent: true, opacity: .11, depthWrite: false});
    for (let latitude = -60; latitude <= 60; latitude += 30) {
        const points = [];
        for (let longitude = -180; longitude <= 180; longitude += 3) points.push(positionAt(latitude, longitude, RADIUS * 1.003));
        scene.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(points), referenceMaterial));
    }
    for (let longitude = -180; longitude < 180; longitude += 45) {
        const points = [];
        for (let latitude = -90; latitude <= 90; latitude += 3) points.push(positionAt(latitude, longitude, RADIUS * 1.003));
        scene.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(points), referenceMaterial));
    }
    const orbit = new THREE.Mesh(new THREE.TorusGeometry(2.14, .003, 5, 240), new THREE.MeshBasicMaterial({color: '#c4d6ce', transparent: true, opacity: .25}));
    orbit.rotation.set(1.18, .23, .28);
    scene.add(orbit);

    const markerGeometry = new THREE.SphereGeometry(.025, 10, 7);
    const markerMaterial = new THREE.MeshBasicMaterial({color: '#ffffff'});
    const markerGroup = new THREE.Group(); scene.add(markerGroup);
    const raycaster = new THREE.Raycaster();
    const pointer = new THREE.Vector2();
    const matrix = new THREE.Matrix4();
    let markerMesh = null, items = [], layer = 'risk', frames = 0, paused = false, visible = true, disposed = false;
    let lastTime = 0, down = null, baseDistance = 6.1, zoomRatio = 1;
    const labelTextures = [];
    const tooltip = document.createElement('div'); tooltip.className = 'orbital-tooltip'; tooltip.hidden = true; host.append(tooltip);

    function render() {
        if (disposed) return;
        renderer.render(scene, camera);
        canvas.dataset.frameCount = String(++frames);
        host.dataset.globeStatus = 'ready';
    }
    function resize() {
        const bounds = host.getBoundingClientRect();
        if (!bounds.width || !bounds.height) return;
        renderer.setSize(bounds.width, bounds.height, false);
        camera.aspect = bounds.width / bounds.height;
        const center = host.parentElement.querySelector('.wb-main')?.getBoundingClientRect();
        const focus = center && innerWidth >= 768 ? center.left + center.width / 2 - bounds.left : bounds.width / 2;
        const availableWidth = center ? center.width : bounds.width;
        baseDistance = 6.1 / Math.min(1, Math.max(.35, availableWidth / (bounds.height * 1.1)));
        camera.position.setLength(baseDistance * zoomRatio);
        markerGroup.children.forEach(child => {if (child.isSprite) child.visible = bounds.width >= 768;});
        camera.setViewOffset(bounds.width, bounds.height, bounds.width / 2 - focus, 0, bounds.width, bounds.height);
        camera.updateProjectionMatrix(); render();
    }
    function animate(time) {
        if (lastTime && time - lastTime < 1000 / 30) return;
        const delta = lastTime ? Math.min((time - lastTime) / 1000, .05) : 1 / 60;
        lastTime = time;
        controls.update(delta);
    }
    function synchronizeMotion() {
        if (disposed) return;
        controls.autoRotate = !paused && !reducedMotion.matches;
        controls.enableDamping = !reducedMotion.matches;
        renderer.setAnimationLoop(visible && !document.hidden && !paused && !reducedMotion.matches ? animate : null);
        canvas.dataset.motion = reducedMotion.matches ? 'reduced' : paused ? 'paused' : 'automatic';
        render();
    }
    function label(text, location) {
        const bitmap = document.createElement('canvas'); bitmap.width = 128; bitmap.height = 64;
        const context = bitmap.getContext('2d');
        context.font = '700 36px Manrope, sans-serif'; context.textAlign = 'center'; context.textBaseline = 'middle';
        context.lineWidth = 4; context.strokeStyle = '#071718'; context.strokeText(text, 64, 32); context.fillStyle = '#f4fff2';
        context.fillText(text, 64, 32);
        const texture = new THREE.CanvasTexture(bitmap); texture.colorSpace = THREE.SRGBColorSpace; labelTextures.push(texture);
        const sprite = new THREE.Sprite(new THREE.SpriteMaterial({map: texture, transparent: true, depthWrite: false}));
        sprite.position.copy(location.clone().normalize().multiplyScalar(RADIUS * 1.045));
        sprite.scale.set(.25, .125, 1); sprite.visible = host.clientWidth >= 768; markerGroup.add(sprite);
    }
    function setData(data) {
        for (const child of [...markerGroup.children]) {markerGroup.remove(child); if (child.isSprite) child.material.dispose();}
        labelTextures.splice(0).forEach(texture => texture.dispose());
        if (markerMesh) markerMesh.dispose();
        items = (data?.results || []).filter(item => Number.isFinite(Number(item.lat)) && Number.isFinite(Number(item.lon)));
        markerMesh = new THREE.InstancedMesh(markerGeometry, markerMaterial, Math.max(1, items.length));
        markerMesh.count = items.length;
        items.forEach((item, index) => {
            const location = positionAt(Number(item.lat), Number(item.lon), RADIUS * 1.015);
            const scale = item.count > 99 ? 2.2 : item.count > 9 ? 1.65 : 1;
            matrix.compose(location, new THREE.Quaternion(), new THREE.Vector3(scale, scale, scale));
            markerMesh.setMatrixAt(index, matrix); markerMesh.setColorAt(index, new THREE.Color(pointColor(item, layer)));
            if (item.count > 1 && items.length <= 80) label(String(item.count), location);
        });
        markerMesh.instanceMatrix.needsUpdate = true;
        if (markerMesh.instanceColor) markerMesh.instanceColor.needsUpdate = true;
        markerMesh.computeBoundingSphere(); markerGroup.add(markerMesh); render();
        canvas.dataset.markerCount = String(items.length);
    }
    function pick(event) {
        if (!markerMesh || !items.length) return null;
        const bounds = canvas.getBoundingClientRect();
        pointer.set((event.clientX - bounds.left) / bounds.width * 2 - 1, -(event.clientY - bounds.top) / bounds.height * 2 + 1);
        raycaster.setFromCamera(pointer, camera);
        const hit = raycaster.intersectObject(markerMesh)[0];
        if (!hit) return null;
        const ground = raycaster.intersectObject(earth)[0];
        return !ground || hit.distance < ground.distance ? items[hit.instanceId] : null;
    }
    canvas.addEventListener('pointerdown', event => {down = {x: event.clientX, y: event.clientY}; tooltip.hidden = true;});
    canvas.addEventListener('pointerup', event => {
        if (down && Math.hypot(event.clientX - down.x, event.clientY - down.y) < 6) {
            const selected = pick(event); if (selected && onSelect) onSelect(selected);
        }
        down = null;
    });
    canvas.addEventListener('pointermove', event => {
        const item = down ? null : pick(event);
        tooltip.hidden = !item;
        canvas.style.cursor = item ? 'pointer' : down ? 'grabbing' : 'grab';
        if (item) {
            tooltip.textContent = item.count ? `${item.count} registry records · mean PCRS ${item.score == null ? 'unavailable' : Number(item.score).toFixed(1)}` : item.bond_id;
            const bounds = host.getBoundingClientRect();
            tooltip.style.left = `${Math.min(event.clientX - bounds.left + 14, bounds.width - 240)}px`;
            tooltip.style.top = `${event.clientY - bounds.top - 38}px`;
        }
    });
    canvas.addEventListener('pointerleave', () => {tooltip.hidden = true; down = null;});
    canvas.addEventListener('keydown', event => {
        if (!['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'].includes(event.key)) return;
        event.preventDefault();
        const spherical = new THREE.Spherical().setFromVector3(camera.position);
        spherical.theta += event.key === 'ArrowLeft' ? .12 : event.key === 'ArrowRight' ? -.12 : 0;
        spherical.phi = THREE.MathUtils.clamp(spherical.phi + (event.key === 'ArrowUp' ? -.12 : event.key === 'ArrowDown' ? .12 : 0), .16, Math.PI - .16);
        camera.position.setFromSpherical(spherical); controls.update(); render();
    });
    canvas.addEventListener('webglcontextlost', event => {event.preventDefault(); if (onFailure) onFailure();});
    controls.addEventListener('change', render);
    const resizeObserver = new ResizeObserver(resize); resizeObserver.observe(host);
    const intersectionObserver = new IntersectionObserver(entries => {visible = entries[0].isIntersecting; synchronizeMotion();});
    intersectionObserver.observe(host);
    document.addEventListener('visibilitychange', synchronizeMotion);
    reducedMotion.addEventListener('change', synchronizeMotion);
    resize(); synchronizeMotion();

    return {
        setData,
        setLayer(value) {layer = value; setData({results: items});},
        setPaused(value) {paused = value; synchronizeMotion();},
        focus(latitude, longitude) {camera.position.copy(positionAt(latitude, longitude).normalize().multiplyScalar(camera.position.length())); controls.update(); render();},
        reset() {zoomRatio = 1; camera.position.copy(originalPosition).setLength(baseDistance); controls.target.set(0, 0, 0); controls.update(); render();},
        zoom(direction) {zoomRatio = THREE.MathUtils.clamp(zoomRatio * (direction > 0 ? .88 : 1.13), .72, 1.3); camera.position.setLength(baseDistance * zoomRatio); controls.update(); render();},
        dispose() {
            disposed = true; renderer.setAnimationLoop(null); controls.dispose(); resizeObserver.disconnect(); intersectionObserver.disconnect();
            document.removeEventListener('visibilitychange', synchronizeMotion); reducedMotion.removeEventListener('change', synchronizeMotion);
            scene.traverse(object => {object.geometry?.dispose(); if (object.material) object.material.dispose();});
            labelTextures.forEach(texture => texture.dispose()); textures.forEach(texture => texture.dispose()); renderer.dispose(); canvas.remove(); tooltip.remove();
        },
    };
}