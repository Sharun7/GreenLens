(() => {
    const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)');
    const finePointer = matchMedia('(hover: hover) and (pointer: fine)');
    const navigation = document.querySelector('.gl-nav');
    const updateNavigation = () => navigation?.classList.toggle('is-scrolled', scrollY > 16);
    addEventListener('scroll', updateNavigation, {passive: true});
    updateNavigation();

    const surfaces = document.querySelectorAll('.wb-kpi');
    surfaces.forEach(surface => {
        surface.dataset.depthSurface = 'true';
        surface.addEventListener('pointermove', event => {
            if (reducedMotion.matches || !finePointer.matches) return;
            const bounds = surface.getBoundingClientRect();
            const horizontal = (event.clientX - bounds.left) / bounds.width - .5;
            const vertical = (event.clientY - bounds.top) / bounds.height - .5;
            surface.style.setProperty('--surface-tilt-x', `${-vertical * 3}deg`);
            surface.style.setProperty('--surface-tilt-y', `${horizontal * 4}deg`);
        });
        surface.addEventListener('pointerleave', () => {
            surface.style.setProperty('--surface-tilt-x', '0deg');
            surface.style.setProperty('--surface-tilt-y', '0deg');
        });
    });

    if ('IntersectionObserver' in window && Element.prototype.animate) {
        let sequence = 0;
        const observer = new IntersectionObserver(entries => {
            entries.forEach(entry => {
                if (!entry.isIntersecting) return;
                observer.unobserve(entry.target);
                if (reducedMotion.matches || document.hidden) return;
                entry.target.animate([
                    {opacity: .45, transform: 'translate3d(0, 12px, 0)'},
                    {opacity: 1, transform: 'translate3d(0, 0, 0)'},
                ], {duration: 540, delay: Math.min(sequence++ * 38, 152), easing: 'cubic-bezier(.2,.65,.25,1)'});
            });
        }, {threshold: .08});
        document.querySelectorAll('.wb-heading, .wb-kpi, .pilot-inspector, .resource-group, .stat-card, .level-card, .portfolio-card, .trust-card, .pipeline-card, .impact-card').forEach(surface => observer.observe(surface));
        addEventListener('pagehide', () => observer.disconnect(), {once: true});
    }

    const total = document.getElementById('wb-total');
    if (total && Element.prototype.animate) {
        const observer = new MutationObserver(() => {
            if (!reducedMotion.matches && !document.hidden) total.animate([
                {color: '#d7f4ad', transform: 'translateY(3px)'},
                {color: '#a8dae5', transform: 'translateY(0)'},
            ], {duration: 360, easing: 'ease-out'});
        });
        observer.observe(total, {childList: true, characterData: true});
        addEventListener('pagehide', () => observer.disconnect(), {once: true});
    }
})();