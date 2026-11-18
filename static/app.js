/* RADAR public web client. Vanilla JS intentionally avoids external install/CDN dependencies. */
'use strict';
const state = { language: localStorage.getItem('radar_language') === 'en' ? 'en' : 'es', globePaused: false, directStory: null, news: [], top: [], sources: [], runs: [], user: null, query: '', category: 'Todas', range: '0', ai: false, carousel: { style: 'Editorial', slides: [], selectedIds: [], selection: 'top5', slideCount: 5 } };
const radarPageSize = 9;
let radarPage = 1;
const $ = (s, root = document) => root.querySelector(s);
const $$ = (s, root = document) => Array.from(root.querySelectorAll(s));
const t = text => state.language === 'en' && Object.hasOwn(englishCopy, text) ? englishCopy[text] : text;
const locale = () => state.language === 'en' ? 'en-US' : 'es-CO';
const sourceCount = n => state.language === 'en' ? `${n} ${n === 1 ? 'source' : 'sources'}` : `${n} ${n === 1 ? 'fuente' : 'fuentes'}`;
const ariaStory = title => (state.language === 'en' ? 'Read ' : 'Leer ') + title;
const localizedSummary = n => n.summary || (state.language === 'en' ? 'Read more at the original source.' : 'Consulta la publicación original para conocer los detalles.');
function localize(root) {
    if (state.language !== 'en') return;
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    for (let node = walker.nextNode(); node; node = walker.nextNode()) {
        const value = node.textContent.trim().replace(/\s+/g, ' ');
        const translated = t(value);
        if (translated !== value) {
            const leading = node.textContent.match(/^\s*/)[0];
            const trailing = node.textContent.match(/\s*$/)[0];
            node.textContent = leading + translated + trailing;
        }
    }
    for (const el of $$('[aria-label], [placeholder], [title]', root)) {
        for (const attr of ['aria-label', 'placeholder', 'title']) {
            const value = el.getAttribute(attr);
            if (value) el.setAttribute(attr, t(value));
        }
    }
}
const safe = (x) => String(x ?? '').replace(/[&<>"']/g, (a) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[a]));
const safeURL = (x) => { if (!x || x === '#') return '#'; const s = String(x).trim(); if (!s || s === '#') return '#'; if (s.startsWith('data:') || s.startsWith('blob:')) return s; try { const u = new URL(s, window.location.origin); return ['https:', 'http:'].includes(u.protocol) ? u.href : '#'; } catch { return '#'; } };
const fmt = x => { try { return new Date(x).toLocaleString(locale(), { dateStyle: 'medium', timeStyle: 'short' }); } catch { return t('Fecha no disponible'); } };
const ago = x => {
    const hours = Math.max(0, Math.floor((Date.now() - new Date(x).getTime()) / 3600000));
    if (!Number.isFinite(hours)) return t('Fecha no disponible');
    if (hours === 0) return state.language === 'en' ? 'Less than an hour ago' : 'Hace menos de 1 h';
    const formatter = new Intl.RelativeTimeFormat(locale(), { numeric: 'always', style: 'short' });
    return hours < 24 ? formatter.format(-hours, 'hour') : formatter.format(-Math.floor(hours / 24), 'day');
};
const labelStatus = (n) => n.is_demo ? 'Ejemplo ficticio' : n.status === 'revision_editorial' ? 'Revisión editorial' : n.status === 'cobertura_multiple' ? 'Cobertura múltiple · no verificada' : 'Fuente única · no verificada';
const pillClass = (n) => n.is_demo ? 'demo' : n.status === 'revision_editorial' ? '' : n.status === 'fuente_unica' ? 'unique' : 'review';
const demoWarning = '<div class="notice warning"><strong>Datos de demostración.</strong> Estos titulares y acontecimientos son ficticios. Para consultar noticias reales, configura fuentes y ejecuta una ronda desde Administración.</div>';
const imageUrl = (n) => {
    const url = safeURL(n?.image_url);
    if (url === '#') return '';
    const parsed = new URL(url);
    return /^https?:$/.test(parsed.protocol) && parsed.pathname === '/' && !parsed.search ? '' : url;
};
const newsImage = (src, className = '', loading = 'lazy') => src
    ? `<img class="${className}" src="${safe(src)}" alt="" loading="${loading}" decoding="async" data-news-image>`
    : '';
const mediaFrame = (n) => {
    if (!n) return '';
    const video = n?.video_url && n.video_url !== '#' ? n.video_url : '';
    const image = imageUrl(n);
    if (video) {
        const yt = (/youtu\.be|youtube\.com/.test(video));
        if (yt) {
            const id = (video.match(/(?:v=|youtu\.be\/|embed\/)([A-Za-z0-9_-]{11})/) || [])[1];
            if (id) { return `<div class="media-card"><iframe class="video-frame" src="https://www.youtube-nocookie.com/embed/${id}" title="Video oficial" loading="lazy" allowfullscreen></iframe></div>`; }
        }
        return `<div class="media-card"><video class="video-frame" controls preload="metadata" ${image ? `poster="${safe(image)}"` : ''}><source src="${safeURL(video)}" type="video/mp4" /></video></div>`;
    }
    if (image) { return `<div class="media-card">${newsImage(image, 'media-hero')}</div>`; }
    return '';
};
function translateMessage(message) {
    const [label, ...detail] = String(message).split(': ');
    return Object.hasOwn(englishCopy, message) ? t(message) : [t(label), ...detail].join(': ');
}
const toast = (msg) => { const t = $('#toast'); t.textContent = translateMessage(msg); t.classList.add('show'); clearTimeout(toast.timer); toast.timer = setTimeout(() => t.classList.remove('show'), 3400); };
async function api(path, opts = {}) { const r = await fetch(path, { credentials: 'same-origin', ...opts, headers: { 'Content-Type': 'application/json', ...(opts.headers || {}) } }); let data; try { data = await r.json(); } catch { data = { detail: 'Respuesta inesperada del servidor' }; } if (!r.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'No fue posible completar la operación'); return data; }
const savedKey = 'radar_saved_stories';
const savedCache = new Map();
function readBookmarks() {
    try {
        const entries = JSON.parse(localStorage.getItem(savedKey) || '[]');
        return new Set(Array.isArray(entries) ? entries.filter(slug => typeof slug === 'string' && slug) : []);
    } catch { return new Set(); }
}
let localBookmarks = readBookmarks();
function storeBookmarks(slugs) {
    localStorage.setItem(savedKey, JSON.stringify([...slugs]));
    localBookmarks = slugs;
}
async function hydrate() {
    try {
        const [items, sources, runs, session, config] = await Promise.all([
            api(`/api/news?limit=90&days=${state.range}&lang=${state.language}`),
            api('/api/sources'), api('/api/runs'), api('/api/auth/me'), api('/api/config'),
        ]);
        Object.assign(state, { news: items.items, top: items.top, sources, runs, user: session.user, ai: config.ai_configured });
    } catch (e) { toast('No se pudo cargar RADAR: ' + e.message); }
}
function header() {
    $('#search-toggle').hidden = location.pathname === '/radar';
    for (const link of $$('.desktop-nav a, .mobile-menu a, .nav-saved')) {
        const active = link.dataset.route === location.pathname;
        link.classList.toggle('active', active);
        if (active) link.setAttribute('aria-current', 'page');
        else link.removeAttribute('aria-current');
    }
}
function storyByline(n) {
    const outlet = n.sources[0]?.name || t('Fuente original');
    return `<span class="story-outlet">${safe(outlet)}</span><time datetime="${safe(n.published_at)}" title="${safe(fmt(n.published_at))}">${safe(ago(n.published_at))}</time>`;
}
function saveLabel(saved) {
    return t(saved ? 'Quitar de guardados' : 'Guardar noticia');
}
function saveButton(n, compact = false) {
    const saved = localBookmarks.has(n.slug);
    return `<button type="button" class="save-story ${compact ? 'round-action' : 'btn btn-light'}${saved ? ' saved' : ''}"
        data-save="${safe(n.slug)}" aria-label="${saveLabel(saved)}" title="${saveLabel(saved)}" aria-pressed="${saved}">
        <span class="save-icon" aria-hidden="true">${saved ? '♥' : '♡'}</span>${compact ? '' : `<span class="save-label">${t(saved ? 'Guardado' : 'Guardar noticia')}</span>`}</button>`;
}
function pageHead(label, title, sub) { return `<section class="page-head"><div class="container"><p class="eyebrow">${safe(label)}</p><h1>${safe(title)}</h1><p>${safe(sub)}</p></div></section>`; }
function topCard(n) { const img = imageUrl(n); return `<a data-route="/noticias/${safe(n.slug)}" href="/noticias/${safe(n.slug)}" class="small-story">${img ? `<div class="small-art" aria-hidden="true">${newsImage(img)}</div>` : ''}<div><div class="card-category">${safe(n.topic)}</div><h3>${safe(n.headline)}</h3><div class="micro">${storyByline(n)}${n.is_demo ? '<span>DEMO</span>' : ''}</div></div></a>`; }
function leadStory(n) {
    const route = '/noticias/' + safe(n.slug);
    const source = imageUrl(n);
    const largePhoto = source.replace(/^(https:\/\/ichef\.bbci\.co\.uk\/ace\/ws\/)240\//, (_, prefix) => prefix + '800/');
    const photo = newsImage(largePhoto || source, 'edition-image', 'eager');
    return `<article class="edition-story${n.headline.length > 105 ? ' edition-long' : ''}"><div class="edition-copy">
        <div class="card-category">${safe(n.topic)}</div>
        <h2><a href="${route}" data-route="${route}">${safe(n.headline)}</a></h2>
        <div class="edition-byline">${storyByline(n)}</div>
        <p>${safe(localizedSummary(n))}</p>
        <div class="edition-actions">
            <a class="btn btn-dark" href="${route}" data-route="${route}">Leer noticia <span aria-hidden="true">→</span></a>
            ${saveButton(n, true)}
        </div>
    </div>${photo ? `<a class="edition-photo" href="${route}" data-route="${route}" aria-label="${safe(ariaStory(n.headline))}" data-photo-fallback="${safe(source !== largePhoto ? source : '')}">${photo}</a>` : ''}</article>`;
}
function feedCard(n) { const img = imageUrl(n); return `<article class="feed-card">${img ? `<a class="feed-art" href="/noticias/${safe(n.slug)}" data-route="/noticias/${safe(n.slug)}" aria-label="${safe(ariaStory(n.headline))}">${newsImage(img)}</a>` : ''}<div class="feed-text"><div class="card-category">${safe(n.topic)} ${n.is_demo ? '· DEMOSTRACIÓN' : ''}</div><h3><a href="/noticias/${safe(n.slug)}" data-route="/noticias/${safe(n.slug)}">${safe(n.headline)}</a></h3><p>${safe(localizedSummary(n))}</p><div class="card-bottom">${storyByline(n)}<span>·</span><span>${safe(labelStatus(n))}</span></div></div>${saveButton(n, true)}</article>`; }
function filters(active) { return `<div class="filters topic-filter" role="group" aria-label="Filtrar noticias por categoría">${['Todas', 'Tecnología', 'Ciencia', 'Economía', 'Clima', 'Salud', 'Educación', 'Política', 'Cultura', 'Deportes', 'Actualidad'].map(c => `<button type="button" class="chip ${active === c ? 'active' : ''}" data-category="${safe(c)}" aria-pressed="${active === c}">${safe(c)}</button>`).join('')}</div>`; }
function historyFilters(active) { return `<div class="filters range-filter" role="group" aria-label="Filtrar por fecha"><button type="button" class="chip ${active === '1' ? 'active' : ''}" data-range="1" aria-pressed="${active === '1'}">24 h</button><button type="button" class="chip ${active === '7' ? 'active' : ''}" data-range="7" aria-pressed="${active === '7'}">7 d</button><button type="button" class="chip ${active === '30' ? 'active' : ''}" data-range="30" aria-pressed="${active === '30'}">30 d</button><button type="button" class="chip ${active === '0' ? 'active' : ''}" data-range="0" aria-pressed="${active === '0'}">Todas las fechas</button></div>`; }
function shownNews() { const q = state.query.toLocaleLowerCase('es'); return state.news.filter(x => (state.category === 'Todas' || x.topic === state.category) && (!q || (x.headline + ' ' + x.summary + ' ' + x.topic).toLocaleLowerCase('es').includes(q))); }
function radarResults() {
    const news = shownNews();
    if (!news.length) return '<div class="empty-state"><h2>Sin resultados</h2><p>Prueba con otra categoría o cambia tu búsqueda.</p><button class="btn btn-dark" data-clear-filters="1">Limpiar filtros</button></div>';
    const pages = Math.ceil(news.length / radarPageSize);
    radarPage = Math.min(radarPage, pages);
    const offset = (radarPage - 1) * radarPageSize;
    const pageLabel = state.language === 'en' ? `Page ${radarPage} of ${pages}` : `Página ${radarPage} de ${pages}`;
    return `<div class="feed-list" id="radar-list">${news.slice(offset, offset + radarPageSize).map(feedCard).join('')}</div>
        ${pages > 1 ? `<nav class="radar-pages" aria-label="Páginas de noticias">
            <button type="button" class="btn btn-light" data-radar-page="${radarPage - 1}" ${radarPage === 1 ? 'disabled' : ''}>← Anterior</button>
            <span>${pageLabel}</span>
            <button type="button" class="btn btn-light" data-radar-page="${radarPage + 1}" ${radarPage === pages ? 'disabled' : ''}>Siguiente →</button>
        </nav>` : ''}`;
}
function refreshFeed() {
    const feed = $('#radar-results');
    if (!feed) return;
    for (const chip of $$('[data-category]')) {
        const active = chip.dataset.category === state.category;
        chip.classList.toggle('active', active);
        chip.setAttribute('aria-pressed', String(active));
    }
    feed.innerHTML = radarResults();
    localize(feed);
    const pageLabel = $('.radar-pages span', feed)?.textContent;
    feed.setAttribute('aria-label', [t('Resultados de noticias'), pageLabel].filter(Boolean).join('. '));
}
function home() {
    const top = (state.top.length ? state.top : state.news).slice(0, 10);
    const first = top.find(imageUrl) || state.news.find(imageUrl) || top[0];
    const more = top.filter(item => item !== first);
    const featured = new Set(top.map(item => item.id));
    if (first) featured.add(first.id);
    const recent = state.news.filter(item => !featured.has(item.id))
        .sort((a, b) => Date.parse(b.published_at) - Date.parse(a.published_at))
        .slice(0, 6);
    const hasDemo = state.news.length > 0 && state.news.every(n => n.is_demo);
    return `<section class="container editorial-home" data-enter>
        <header class="edition-band">
            <div class="edition-intro">
                <h1 class="edition-name">Noticias <span>en contexto</span></h1>
                <p>Sigue la actualidad y consulta las fuentes originales.</p>
                <a class="btn btn-light" href="/radar" data-route="/radar">Explorar el Radar <span aria-hidden="true">→</span></a>
            </div>
            <div class="hero-art edition-globe">
                <div class="globe-scene" aria-hidden="true">
                    <span class="globe-ring"></span><span class="globe-ring globe-ring-secondary"></span>
                    <img src="/assets/hero-globe.svg" width="720" height="650" alt="" fetchpriority="high">
                </div>
                <button type="button" class="globe-control" id="globe-control" aria-label="Pausar globo" title="Pausar globo">
                    <svg class="globe-pause" viewBox="0 0 24 24" width="20" aria-hidden="true"><path d="M9 5v14M15 5v14"/></svg>
                    <svg class="globe-play" viewBox="0 0 24 24" width="20" aria-hidden="true" hidden><path d="m9 5 11 7-11 7z"/></svg>
                </button>
            </div>
        </header>
        ${hasDemo ? demoWarning : ''}
        ${first ? leadStory(first) : '<p class="edition-empty">Aún no hay noticias destacadas.</p>'}
    </section>
    <div class="main-surface">
        <section class="container top-section" ${more.length ? '' : 'hidden'}>
            <div class="section-heading"><h2>Destacadas</h2><a class="link-arrow" href="/radar" data-route="/radar">Ver todas <span aria-hidden="true">→</span></a></div>
            ${more.length ? `<div class="edition-stories">${more.slice(0, 3).map(topCard).join('')}</div>` : ''}
            ${more.length > 3 ? `<details class="more-stories"><summary>Más destacadas</summary><div class="right-stories">${more.slice(3).map(topCard).join('')}</div></details>` : ''}
        </section>
        ${recent.length ? `<section class="container">
            <div class="section-heading latest-heading"><h2>Últimas noticias</h2></div>
            <div id="feed-list">${recent.map(feedCard).join('')}</div>
            <div class="home-feed-end"><a class="btn btn-light" href="/radar" data-route="/radar">Ver todas las noticias →</a></div>
        </section>` : ''}
    </div>`;
}
function radar() {
    return `<section class="container content-area radar-layout"><div class="radar-main">
        <h1>Radar de noticias</h1>
        <div class="toolbar"><div class="search-shell"><svg viewBox="0 0 24 24" width="20" aria-hidden="true"><circle cx="10.8" cy="10.8" r="7.3"/><path d="m16.2 16.2 5 5"/></svg><input id="radar-search" type="search" value="${safe(state.query)}" placeholder="Buscar noticias" aria-label="Buscar noticias"></div>${historyFilters(state.range)}</div>
        ${filters(state.category)}
        <div id="radar-results" role="region" tabindex="-1" aria-label="Resultados de noticias">${radarResults()}</div>
    </div></section>`;
}
function renderCarouselSlide(slide) { const image = newsImage(imageUrl(slide), 'carousel-image'); const label = slide.layout === 'cover' ? 'Portada' : slide.layout === 'context' ? 'Contexto' : slide.layout === 'close' ? 'Cierre' : 'Noticia'; return `<article class="carousel-slide ${safe(slide.layout)}"><div class="carousel-topbar"><span class="carousel-brand">RADAR</span><span>${safe(slide.category || 'Actualidad')}</span><span class="slide-number">${String(slide.index).padStart(2, '0')}</span></div><div class="carousel-media"><div class="carousel-graphic" aria-hidden="true"><span>RADAR</span></div>${image}</div><div class="carousel-copy"><p class="carousel-kicker">${safe(label)}</p><h3>${safe(slide.headline)}</h3><p>${safe(slide.summary)}</p></div><div class="carousel-footer"><span>${safe(slide.source || 'RADAR')}</span><span>${safe(slide.date || 'Fuente original')}</span></div></article>`; }
function newsletters() { const topNews = state.top.length ? state.top : state.news.slice(0, 5); const selectedIds = state.carousel.selectedIds?.length ? state.carousel.selectedIds : topNews.map(n => n.id); const options = topNews.map(n => `<label class="carousel-news-option"><input type="checkbox" data-carousel-news="${n.id}" ${selectedIds.includes(n.id) ? 'checked' : ''} /><span>${safe(n.headline)}</span></label>`).join(''); const previews = state.carousel.slides?.length ? state.carousel.slides.map(renderCarouselSlide).join('') : '<div class="empty-state">Genera un carrusel para ver la vista previa.</div>'; return `${pageHead('Selección editorial', 'Crear carrusel para Instagram', 'Prepara una selección de noticias y descárgala en ZIP.')}<section class="container content-area"><div class="carousel-builder"><div class="carousel-panel"><div class="editorial-bar" style="padding-top:0"><div><span class="label">Generador editorial</span><h2 class="section-title">Carrusel de Instagram</h2></div></div><div class="field-row"><label class="field"><span>Tipo de selección</span><select id="carousel-selection"><option value="top5" ${state.carousel.selection === 'top5' ? 'selected' : ''}>Top 5 automático</option><option value="manual" ${state.carousel.selection === 'manual' ? 'selected' : ''}>Selección manual</option></select></label><label class="field"><span>Diapositivas</span><select id="carousel-slides"><option value="3" ${state.carousel.slideCount === 3 ? 'selected' : ''}>3</option><option value="5" ${state.carousel.slideCount === 5 ? 'selected' : ''}>5</option><option value="7" ${state.carousel.slideCount === 7 ? 'selected' : ''}>7</option><option value="8" ${state.carousel.slideCount === 8 ? 'selected' : ''}>8</option><option value="10" ${state.carousel.slideCount === 10 ? 'selected' : ''}>10</option></select></label><label class="field"><span>Estilo</span><select id="carousel-style"><option value="Editorial" ${state.carousel.style === 'Editorial' ? 'selected' : ''}>Editorial</option><option value="Moderno" ${state.carousel.style === 'Moderno' ? 'selected' : ''}>Moderno</option><option value="Minimalista" ${state.carousel.style === 'Minimalista' ? 'selected' : ''}>Minimalista</option></select></label></div><div class="field"><span>Noticias para incluir</span><div class="carousel-news-grid" id="carousel-selector">${options}</div></div><div class="carousel-actions"><button type="button" class="btn btn-mint" id="generate-carousel">Generar carrusel</button><button type="button" class="btn btn-dark" id="download-carousel" ${state.carousel.slides?.length ? '' : 'disabled'}>Descargar ZIP</button></div></div><div class="carousel-preview-panel" id="carousel-preview"><div class="editorial-bar"><div><span class="label">Vista previa</span><h2 class="section-title">${t('Diapositivas')} ${state.carousel.slides?.length ? state.carousel.slides.length : '0'}</h2></div></div><div class="carousel-previews">${previews}</div></div></div></section>`; }
function sourcesView() { return `${pageHead('Trazabilidad', 'Directorio de fuentes', 'Consulta los RSS registrados y sus condiciones de reutilización antes de interpretar una noticia.')}<section class="container content-area"><div class="notice">Un feed disponible no significa autorización para copiar artículos completos, imágenes o vídeos. Cada fuente debe cumplir sus términos de uso.</div><div class="info-grid">${state.sources.map(s => `<article class="info-card"><span class="label">RSS · ${safe(t(s.region))}</span><h3>${safe(s.name)}</h3><p>${safe(t(s.rights_note))}</p><p style="word-break:break-all;font-size:11px">${safe(s.feed_url)}</p><a class="link-arrow" href="${safe(safeURL(s.homepage || s.feed_url))}" target="_blank" rel="noopener noreferrer">Visitar fuente original ↗</a></article>`).join('')}</div><div class="notice" style="margin-top:30px">Las nuevas fuentes se agregan desde Administración; el propietario debe revisar permisos, reputación y condiciones técnicas.</div></section>`; }
function methodology() { return `${pageHead('Cómo funciona', 'Metodología y transparencia', 'Cada paso está pensado para separar la procedencia de la información de una afirmación de veracidad.')}<section class="container content-area"><div class="info-grid"><article class="info-card"><h3>01. Recolección</h3><p>Consultamos RSS configurados. Registramos título, descripción disponible, publicación y enlace original.</p></article><article class="info-card"><h3>02. Agrupación</h3><p>Eliminamos URLs repetidas y agrupamos titulares similares. La versión inicial no garantiza identificación semántica perfecta.</p></article><article class="info-card"><h3>03. Revisión</h3><p>El número de medios se muestra como cobertura, nunca como porcentaje de verdad. Los temas sensibles pasan a revisión humana.</p></article><article class="info-card"><h3>04. IA opcional</h3><p>Gemini puede generar un borrador cuando hay varias fuentes. Los borradores quedan sin publicación automática hasta ser revisados.</p></article><article class="info-card"><h3>05. Respaldo</h3><p>Cuando Gemini no responde, conservamos el titular original, atribuido. El sistema evita fabricar un artículo.</p></article><article class="info-card"><h3>06. Selección</h3><p>La prioridad combina actualidad y cobertura. El Top 5 no pretende ser una medición objetiva e infalible de relevancia.</p></article></div><div class="legal" style="margin-top:35px"><h2>Qué significa cada etiqueta</h2><p><b>Fuente única:</b> una fuente registrada, sin corroboración independiente en el sistema.</p><p><b>Cobertura múltiple:</b> dos o más medios asociados. No prueba veracidad por sí misma.</p><p><b>Revisión editorial:</b> una persona habilitó la publicación; no constituye certificación absoluta.</p><p><b>Ejemplo ficticio:</b> contenido creado únicamente para probar la interfaz.</p><h2>Correcciones y ética</h2><p>RADAR no debe inventar declaraciones, cifras, fechas o vínculos causales. Se respetan los derechos de autor y se prohíbe publicar automáticamente acusaciones personales o material que requiera evaluación sensible. Los resúmenes asistidos por IA deben estar identificados.</p><p>La plataforma está inspirada en el Proyecto 3 del material académico del profesor. El cuaderno original se conserva en la carpeta docs/.</p></div></section>`; }
function details(slug) { const n = state.news.find(x => x.slug === slug) || state.top.find(x => x.slug === slug) || (state.directStory?.slug === slug ? state.directStory : savedCache.get(slug)); if (n && n.language !== state.language) return unavailableStory(n); if (!n) return `${pageHead('Noticia no encontrada', 'Registro no disponible', 'Puede haberse retirado para revisión editorial.')}<div class="container content-area"><a class="btn btn-dark" data-route="/radar" href="/radar">Volver al Radar</a></div>`; const mediaBlock = mediaFrame(n); const evidenceHtml = n.evidence?.length ? n.evidence.map(x => `<div class="evidence-card"><p>${safe(x.claim)}</p><small>${safe(x.source || 'Fuente asociada')}</small></div>`).join('') : '<div class="notice">No se registran evidencias verificadas para este caso todavía.</div>'; return `<section class="container content-area story-content"><a class="link-arrow story-back" href="/radar" data-route="/radar">← Radar de noticias</a><div class="story-detail">${n.is_demo ? demoWarning : ''}<div class="body-head"><span class="label">${safe(n.topic)} · ${safe(ago(n.published_at))}</span><h1>${safe(n.headline)}</h1><p class="deck">${safe(localizedSummary(n))}</p>${mediaBlock}<div class="detail-badges"><span class="status-pill ${pillClass(n)}">${safe(labelStatus(n))}</span><span class="meta-update">${sourceCount(n.sources.length)}</span><span class="meta-update">${state.language === 'en' ? 'Updated:' : 'Actualizado:'} ${fmt(n.updated_at)}</span>${saveButton(n)}</div></div><div class="detail-grid"><div class="detail-main"><div class="notice ${n.is_demo ? 'warning' : ''}"><strong>${n.is_demo ? 'EJEMPLO FICTICIO' : 'Aviso editorial:'}</strong> ${n.is_demo ? 'Este acontecimiento no es real. Sirve para probar el diseño.' : 'La existencia de fuentes no garantiza la verdad de los hechos. Consulta la publicación original antes de compartir.'}</div><h2>Lectura rápida</h2><p>${safe(localizedSummary(n))}</p><h2>Fuentes originales</h2><div class="sources-list">${n.sources.map((s, i) => `<div class="source-entry"><div><strong>${i + 1}. ${safe(s.name)}</strong><small>${fmt(s.published_at)}</small></div><a href="${safe(safeURL(s.url))}" target="_blank" rel="noopener noreferrer">Abrir ↗</a></div>`).join('') || '<p>No hay fuentes disponibles.</p>'}</div><h2>Hechos y evidencias</h2>${n.evidence.length ? n.evidence.map(x => `<div class="notice"><p>${safe(x.claim)}</p><small>Referencias del borrador: ${safe((x.source_ids || []).join(', '))}. Pendiente de comprobación editorial independiente.</small></div>`).join('') : '<div class="notice warning">Sin afirmaciones verificadas individualmente. Consulta los titulares originales.</div>'}<h2>Cómo evolucionó</h2><div class="timeline">${n.timeline.map(item => `<div class="timeline-item"><strong>${safe(state.language === 'en' ? item.label.replace(/^Publicación registrada:/, 'Publication recorded:') : item.label)}</strong><small>${fmt(item.at)}</small></div>`).join('') || '<p>Sin eventos registrados</p>'}</div></div><aside><div class="aside-card"><span class="label">Transparencia</span><h3>Ficha editorial</h3><div class="aside-stat"><span>Tipo de redacción</span><strong style="font-size:12px">${safe(n.mode.replaceAll('_', ' '))}</strong></div><div class="aside-stat"><span>Tono</span><strong style="font-size:11px">${safe(n.editorial_tone)}</strong></div><div class="aside-stat"><span>Estado</span><strong style="font-size:12px">${safe(t(labelStatus(n)))}</strong></div><p>${n.mode === 'titular_atribuido' ? 'En esta versión se conserva la atribución al medio; no se genera un resumen independiente sin datos suficientes.' : 'Borrador o resumen disponible con trazabilidad a entradas RSS.'}</p><a class="guide-link" href="/metodologia" data-route="/metodologia">Ver metodología ↗</a></div><div class="aside-card"><h3>Comparar cobertura</h3><p>Revisa cómo titula cada medio. Si las fuentes discrepan, consulta sus artículos completos.</p><div class="aside-stat"><span>Fuentes listadas</span><strong>${n.sources.length}</strong></div></div></aside></div><div style="margin-top:46px"><a class="btn btn-dark" href="/radar" data-route="/radar">← Volver al Radar</a></div></div></section>`; }
function auth() {
    return `<section class="auth-layout container">
        <div class="auth-intro"><h1>Acceso editorial</h1><p>Ingresa con tu cuenta para administrar RADAR.</p></div>
        <div class="form-panel auth-panel">
            <form id="auth-form">
                <div class="field"><label for="auth-email">Correo electrónico</label><input id="auth-email" type="email" autocomplete="email" required name="email"></div>
                <div class="field"><label for="auth-password">Contraseña</label><input id="auth-password" type="password" autocomplete="current-password" required maxlength="150" name="password"></div>
                <button class="btn btn-mint auth-submit" type="submit">Iniciar sesión</button>
                <div id="auth-error" role="alert"></div>
            </form>
        </div>
    </section>`;
}
function account() { if (!state.user) return auth(); return `${pageHead('Tu cuenta', 'Mi espacio', 'Gestiona tu acceso y consulta tus lecturas guardadas.')}<section class="container content-area"><div class="form-panel"><h2>${safe(state.user.email)}</h2><p>${state.language === 'en' ? 'Role:' : 'Rol:'} ${safe(state.user.role === 'admin' ? t('Administrador') : t('Lector'))}</p><div style="display:flex;gap:10px;flex-wrap:wrap;margin-top:25px"><a class="btn btn-dark" href="/guardados" data-route="/guardados">♡ Mis guardados</a><button type="button" class="btn btn-light" data-import-saved>Importar guardados de la cuenta</button>${state.user.role === 'admin' ? '<a class="btn btn-mint" href="/admin" data-route="/admin">Administrar noticias</a>' : ''}<button class="btn btn-light" id="logout-btn">Cerrar sesión</button></div><div style="margin-top:35px;border-top:1px solid #dce2de;padding-top:18px"><h2>Cambiar contraseña</h2><form id="change-password-form"><div class="field"><label>Contraseña actual</label><input name="old_password" type="password" autocomplete="current-password" required></div><div class="field"><label>Contraseña nueva (mínimo 10 caracteres)</label><input name="new_password" type="password" minlength="10" autocomplete="new-password" required></div><button type="submit" class="btn btn-dark">Guardar nueva contraseña</button></form></div>${state.user.role === 'reader' ? '<div style="margin-top:28px"><h2>Eliminar mi cuenta</h2><p>Eliminar la cuenta borra el registro de usuario y los guardados asociados a la cuenta.</p><form id="delete-account-form"><div class="field"><label>Confirma tu contraseña</label><input name="password" type="password" autocomplete="current-password" required></div><button type="submit" class="btn btn-light">Eliminar mi cuenta</button></form></div>' : ''}</div></section>`; }
function saved() {
    return `<section class="container content-area"><h1>Noticias guardadas</h1>
        <p>Tus guardados se conservan en este navegador.</p>
        <div id="saved-stories" aria-live="polite"></div></section>`;
}
async function loadSavedStories() {
    const container = $('#saved-stories');
    if (!container) return;
    const wanted = [...localBookmarks];
    const current = new Map([...savedCache, ...[...state.news, ...state.top].map(item => [item.slug, item])]);
    const missing = wanted.filter(slug => !current.has(slug));
    if (missing.length) {
        container.textContent = t('Cargando guardados…');
        const results = await Promise.allSettled(missing.map(slug => api('/api/news/' + encodeURIComponent(slug))));
        if (!container.isConnected) return;
        for (const result of results) {
            if (result.status !== 'fulfilled') continue;
            const item = result.value;
            current.set(item.slug, item);
            savedCache.set(item.slug, item);
        }
    }
    const items = [...localBookmarks].map(slug => current.get(slug)).filter(item => item?.language === state.language);
    const empty = [...localBookmarks].some(slug => current.has(slug))
        ? 'Aún no tienes guardados en este idioma.'
        : 'Aún no tienes guardados';
    container.innerHTML = items.length
        ? `<div class="feed-list saved-list">${items.map(feedCard).join('')}</div>`
        : `<div class="empty-state"><h2>${empty}</h2><a class="btn btn-dark" href="/radar" data-route="/radar">Ver noticias</a></div>`;
    localize(container);
}
function admin() { if (!state.user || state.user.role !== 'admin') return `${pageHead('Administración', 'Acceso restringido', 'Necesitas una cuenta con permiso de editor.')}<section class="container content-area"><a class="btn btn-dark" href="/acceso" data-route="/acceso">Iniciar sesión</a></section>`; return `${pageHead('Panel editorial', 'Centro de operaciones', 'Gestiona fuentes, solicita consultas RSS y decide qué borradores pueden publicarse.')}<section class="container content-area"><div class="admin-grid"><div class="admin-kpi"><strong>${state.news.length}</strong><span>Registros públicos visibles</span></div><div class="admin-kpi"><strong>${state.sources.length}</strong><span>Fuentes configuradas</span></div><div class="admin-kpi"><strong>${state.runs.length}</strong><span>Últimas ejecuciones visibles</span></div><div class="admin-kpi"><strong>${state.ai ? 'API' : 'LOCAL'}</strong><span>Modo de procesamiento</span></div></div><div class="admin-cols"><section class="admin-box"><h2>Recolectar noticias reales</h2><p>Consulta las fuentes RSS. Si falla la conexión, el portal conserva los últimos datos disponibles.</p><button class="btn btn-mint" id="collect-btn">↻ Ejecutar ronda ahora</button><div id="collect-result" aria-live="polite"></div><p class="notice warning">Los borradores con IA y temas sensibles pasan a revisión. No se publican automáticamente.</p></section><section class="admin-box"><h2>Agregar una fuente RSS</h2><form id="source-form"><div class="field"><label>Nombre del medio o feed</label><input name="name" required minlength="3" placeholder="Nombre de la fuente"/></div><div class="field"><label>URL RSS HTTPS</label><input name="feed_url" type="url" required placeholder="https://ejemplo.com/rss"/></div><div class="field"><label>Página principal</label><input name="homepage" type="url" placeholder="https://ejemplo.com/"/></div><div class="field"><label>Observación de licencia</label><input name="rights_note" placeholder="Revisar términos de uso"/></div><button type="submit" class="btn btn-dark">+ Agregar fuente</button></form></section></div><section class="admin-box" style="margin-top:22px"><div class="section-heading"><div><h2>Noticias pendientes de revisión</h2><p>Borradores y registros sensibles no aparecen públicamente hasta aprobación.</p></div></div><div id="pending-list" class="loading-shell">Cargando pendientes...</div></section><section class="admin-box" style="margin-top:22px"><h2>Últimas rondas</h2><div>${state.runs.length ? state.runs.map(r => `<div class="aside-stat"><span>${safe(fmt(r.at))} · ${r.fetched} titulares leídos</span><strong>${r.new_count} nuevos</strong></div>`).join('') : 'Aún no se han ejecutado rondas.'}</div></section></section>`; }
function legal(type) { const terms = type === 'terminos'; return `${pageHead('Transparencia', terms ? 'Términos de uso' : 'Política de privacidad', 'Texto inicial para la versión local; requiere revisión jurídica antes de un lanzamiento público.')}<section class="container content-area"><article class="legal"><div class="notice warning">Documento preliminar. No debe presentarse como asesoría legal ni como política definitiva de producción.</div>${terms ? `<h2>1. Alcance</h2><p>RADAR es un proyecto de seguimiento y organización de noticias. No certifica hechos, no sustituye el periodismo profesional ni asume autoría de contenidos enlazados.</p><h2>2. Fuentes y atribución</h2><p>Los titulares y enlaces conservan su medio de origen. La consulta de cada publicación se realiza directamente en los sitios de los titulares.</p><h2>3. Cuentas</h2><p>Al registrarte, aceptas utilizar una contraseña privada y no intentar acceder a funciones administrativas sin permiso.</p><h2>4. Contenido generado con IA</h2><p>Los resúmenes elaborados con IA se señalan y son sujetos de procesos de revisión editorial; no representan prueba definitiva de veracidad.</p>` : `<h2>1. Datos tratados</h2><p>Para crear una cuenta se guarda correo electrónico, contraseña cifrada mediante hash y fecha de aceptación de los términos. Los guardados de lectura se almacenan en tu navegador.</p><h2>2. Cookies</h2><p>Se utiliza una cookie de sesión esencial y preferencias de cookies almacenadas localmente. Esta versión no instala rastreadores de publicidad ni análisis de terceros.</p><h2>3. Finalidad</h2><p>El sistema utiliza los datos de las cuentas para gestionar el acceso y la administración del servicio.</p><h2>4. Derechos</h2><p>Antes de publicar una versión pública deberá habilitarse un contacto y procedimiento para solicitudes de consulta, corrección y eliminación de datos conforme a la legislación aplicable.</p>`}<p><a href="/metodologia" data-route="/metodologia" class="text-link">Consultar metodología de noticias</a></p></article></section>`; }
function render() {
    const path = decodeURIComponent(location.pathname); let html;
    if (path === '/') html = home(); else if (path === '/radar') html = radar(); else if (path === '/boletines') html = newsletters(); else if (path === '/fuentes') html = sourcesView(); else if (path === '/metodologia') html = methodology(); else if (path === '/acceso') html = state.user ? account() : auth(); else if (path === '/cuenta') html = account(); else if (path === '/guardados') html = saved(); else if (path === '/admin') html = admin(); else if (path === '/terminos' || path === '/privacidad') html = legal(path.slice(1)); else if (path.startsWith('/noticias/')) html = details(path.split('/')[2]); else html = pageHead('404', 'Página no encontrada', 'La dirección que buscas no existe.') + '<div class="container content-area"><a href="/" data-route="/" class="btn btn-dark">Ir al inicio</a></div>';
    $('#main').innerHTML = html;
    localize($('#main')); document.title = t(path === '/' ? 'Inicio' : path === '/radar' ? 'Radar' : path === '/boletines' ? 'Carrusel' : 'RADAR') + (state.language === 'en' ? ' | RADAR News' : ' | RADAR Noticias'); header(); initGlobe(); if (path === '/guardados') loadSavedStories(); if (path === '/admin' && state.user?.role === 'admin') loadPending();
}
function toggleHeaderPanel(panel, open) {
    const menu = panel === 'menu';
    const button = menu ? $('#menu-button') : $('#search-toggle');
    button.setAttribute('aria-expanded', String(open));
    if (menu) {
        $('#mobile-menu').hidden = !open;
        button.setAttribute('aria-label', t(open ? 'Cerrar navegación' : 'Abrir navegación'));
    } else {
        $('#global-search-form').hidden = !open;
        button.setAttribute('aria-label', t(open ? 'Cerrar búsqueda' : 'Abrir búsqueda'));
    }
}
function navigate(path) {
    if (!path) return;
    history.pushState({}, '', path);
    toggleHeaderPanel('menu', false);
    toggleHeaderPanel('search', false);
    render();
    $('#main').focus({ preventScroll: true });
    window.scrollTo({ top: 0, behavior: 'instant' });
}
function motionAllowed() {
    return document.documentElement.dataset.motion !== 'reduced' && !matchMedia('(prefers-reduced-motion: reduce)').matches;
}
function initPreferences() {
    $('#language-preference').value = state.language;
    const preference = $('#motion-preference');
    preference.value = localStorage.getItem('radar_motion') === 'reduced' ? 'reduced' : 'auto';
    document.documentElement.dataset.motion = preference.value;
    preference.addEventListener('change', () => {
        document.documentElement.dataset.motion = preference.value;
        localStorage.setItem('radar_motion', preference.value);
    });
    $('#language-preference').addEventListener('change', event => {
        localStorage.setItem('radar_language', event.target.value);
        location.reload();
    });
}
function initGlobe() {
    const art = $('.hero-art');
    if (!art) return;
    const control = $('#globe-control');
    const updatePlayback = () => {
        const label = t(state.globePaused ? 'Reanudar globo' : 'Pausar globo');
        art.toggleAttribute('data-paused', state.globePaused);
        control.setAttribute('aria-label', label);
        control.title = label;
        $('.globe-pause', control).toggleAttribute('hidden', state.globePaused);
        $('.globe-play', control).toggleAttribute('hidden', !state.globePaused);
    };
    updatePlayback();
    let origin = null;
    let rotation = 0;
    const point = value => art.style.setProperty('--tilt-y', value + 'deg');
    art.addEventListener('pointerdown', event => {
        if (!motionAllowed() || event.target.closest('button') || event.button !== 0 || !event.isPrimary) return;
        origin = event.clientX;
        art.setAttribute('data-dragging', '');
        art.setPointerCapture(event.pointerId);
    });
    art.addEventListener('pointermove', event => {
        if (origin === null || !motionAllowed()) return;
        point(Math.max(-40, Math.min(40, rotation + (event.clientX - origin) * .25)));
    });
    art.addEventListener('pointerup', event => {
        if (origin !== null && motionAllowed()) {
            rotation = Math.max(-40, Math.min(40, rotation + (event.clientX - origin) * .25));
        }
    });
    for (const event of ['pointerup', 'pointercancel', 'lostpointercapture']) {
        art.addEventListener(event, () => {
            origin = null;
            art.removeAttribute('data-dragging');
            point(rotation);
        });
    }
    control.addEventListener('click', () => {
        if (!motionAllowed()) return;
        state.globePaused = !state.globePaused;
        updatePlayback();
    });
}
function cookieDialog(force = false) {
    if (!force && localStorage.getItem('radar_cookie_choice')) return;
    const root = $('#cookie-root');
    root.innerHTML = `<dialog class="cookie-card" aria-labelledby="cookie-title">
        <h2 id="cookie-title">Preferencias de cookies</h2>
        <p>RADAR usa cookies esenciales para mantener tu sesión. Puedes elegir si permites cookies opcionales en el futuro.</p>
        <details class="cookie-switches">
            <summary>Personalizar</summary>
            <label class="input-inline"><input id="cookie-optional" type="checkbox"> Permitir cookies opcionales</label>
            <button class="btn btn-light" data-cookie="config">Guardar selección</button>
        </details>
        <a class="text-link" href="/privacidad" data-route="/privacidad">Política de privacidad</a>
        <div class="cookie-actions">
            <button class="btn btn-light" data-cookie="reject">Solo esenciales</button>
            <button class="btn btn-mint" data-cookie="accept">Aceptar opcionales</button>
        </div>
    </dialog>`;
    localize(root);
    $('dialog', root).showModal();
}
function saveCookie(choice) { const optional = choice === 'accept' || (choice === 'config' && $('#cookie-optional')?.checked); localStorage.setItem('radar_cookie_choice', JSON.stringify({ optional, at: new Date().toISOString() })); $('#cookie-root').innerHTML = ''; toast('Preferencias de cookies guardadas'); }
async function loadPending() { const el = $('#pending-list'); try { const items = await api('/api/admin/pending'); el.classList.remove('loading-shell'); el.innerHTML = items.length ? items.map(n => `<div class="pending-entry"><b>${safe(n.headline)}</b><small>${safe(n.topic)} · ${sourceCount(n.sources.length)} · ${safe(n.draft_pending ? 'PROPUESTA DE REDACCIÓN IA' : 'REVISIÓN SENSIBLE')} · ${safe(n.sensitivity_reason || 'Comparar borrador con fuentes')}</small>${n.draft_pending ? `<div class="notice"><b>Propuesta IA (aún no publicada):</b><p>${safe(n.draft_headline)}</p><p>${safe(n.draft_summary)}</p></div>` : ''}<div class="actions" style="margin-top:12px"><button class="btn btn-mint btn-sm" data-review="approve" data-news-id="${n.id}">Aprobar tras revisar fuentes</button><button class="btn btn-light btn-sm" data-review="reject" data-news-id="${n.id}">Rechazar</button>${n.sources[0] ? `<a class="btn btn-light btn-sm" href="${safe(safeURL(n.sources[0].url))}" target="_blank" rel="noopener noreferrer">Fuente ↗</a>` : ''}</div></div>`).join('') : '<div class="success-note">No hay borradores pendientes.</div>'; localize(el); } catch (e) { el.textContent = translateMessage(e.message); } }
async function clickAction(e) {
    if (e.target.closest('#settings-button')) {
        toggleHeaderPanel('menu', false);
        toggleHeaderPanel('search', false);
        $('#preferences-dialog').showModal();
        return;
    }
    const switchLanguage = e.target.closest('[data-language]');
    if (switchLanguage) {
        localStorage.setItem('radar_language', switchLanguage.dataset.language);
        location.reload();
        return;
    }
    const route = e.target.closest('[data-route]'); if (route) { if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return; e.preventDefault(); $('#cookie-root dialog[open]')?.close(); navigate(route.dataset.route); return; }
    const page = e.target.closest('[data-radar-page]');
    if (page && !page.disabled) {
        radarPage = Number(page.dataset.radarPage);
        refreshFeed();
        const results = $('#radar-results');
        results.focus({ preventScroll: true });
        results.scrollIntoView({ block: 'start', behavior: 'instant' });
        return;
    }
    const cat = e.target.closest('[data-category]'); if (cat) { state.category = cat.dataset.category; radarPage = 1; refreshFeed(); return; }
    const range = e.target.closest('[data-range]'); if (range) { state.range = String(range.dataset.range || '30'); radarPage = 1; hydrate().then(() => render()); return; }
    const cookie = e.target.closest('[data-cookie]'); if (cookie) { saveCookie(cookie.dataset.cookie); return; }
    if (e.target.closest('#cookie-settings-footer')) { cookieDialog(true); return; }
    const headerButton = e.target.closest('#menu-button, #search-toggle');
    if (headerButton) {
        const panel = headerButton.id === 'menu-button' ? 'menu' : 'search';
        const open = headerButton.getAttribute('aria-expanded') !== 'true';
        toggleHeaderPanel(panel === 'menu' ? 'search' : 'menu', false);
        toggleHeaderPanel(panel, open);
        if (open && panel === 'search') $('#global-search').focus();
        return;
    }
    if (e.target.closest('[data-clear-filters]')) {
        state.category = 'Todas';
        state.query = '';
        radarPage = 1;
        $('#global-search').value = '';
        const input = $('#radar-search');
        if (input) input.value = '';
        refreshFeed();
        (input || $('[data-category="Todas"]'))?.focus();
        return;
    }
    if (e.target.closest('#generate-carousel')) {
        const selection = $('#carousel-selection')?.value || 'top5';
        const slides = Number($('#carousel-slides')?.value || 5);
        const style = $('#carousel-style')?.value || 'Editorial';
        const selected = $$('#carousel-selector [data-carousel-news]:checked').map(box => Number(box.dataset.carouselNews));
        const payload = { selection, slides, style, lang: state.language, news_ids: selection === 'manual' ? selected : [] };
        const trigger = $('#generate-carousel');
        trigger.disabled = true;
        try {
            const result = await api('/api/carousel/generate', { method: 'POST', body: JSON.stringify(payload) });
            state.carousel = { ...state.carousel, slides: result.slides || [], style: result.style || style, selection, slideCount: slides, selectedIds: selection === 'manual' ? selected : (state.top.slice(0, 5).map(n => n.id)) };
            render();
            toast(result.count ? 'Previsualización del carrusel actualizada' : 'Aún no hay noticias en este idioma.');
            if (result.count && matchMedia('(max-width: 980px)').matches) {
                $('#carousel-preview').scrollIntoView({ block: 'start', behavior: motionAllowed() ? 'smooth' : 'instant' });
            }
        } catch (ex) { toast(ex.message); }
        finally { trigger.disabled = false; }
        return;
    }
    if (e.target.closest('#download-carousel')) {
        if (!state.carousel.slides?.length) { toast('Primero genera un carrusel.'); return; }
        try {
            const response = await fetch('/api/carousel/export', { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ deck: state.carousel.slides, style: state.carousel.style || 'Editorial' }) });
            if (!response.ok) throw new Error('No se pudo generar el ZIP');
            const blob = await response.blob();
            const url = URL.createObjectURL(blob);
            const anchor = document.createElement('a');
            anchor.href = url;
            anchor.download = 'radar-carrusel.zip';
            anchor.click();
            URL.revokeObjectURL(url);
            toast('ZIP descargado');
        } catch (ex) { toast(ex.message); }
        return;
    }
    if (e.target.closest('#logout-btn')) { await api('/api/auth/logout', { method: 'POST' }); state.user = null; toast('Sesión cerrada'); navigate('/'); return; }
    if (e.target.closest('[data-import-saved]')) {
        const { slugs } = await api('/api/bookmarks');
        storeBookmarks(new Set([...localBookmarks, ...slugs]));
        toast(slugs.length ? 'Guardados importados' : 'No hay guardados en la cuenta');
        return;
    }
    const save = e.target.closest('[data-save]');
    if (save) {
        const slug = save.dataset.save;
        const next = readBookmarks();
        const added = !next.has(slug);
        if (added) next.add(slug);
        else next.delete(slug);
        storeBookmarks(next);
        for (const button of $$('[data-save]').filter(item => item.dataset.save === slug)) {
            const label = saveLabel(added);
            button.classList.toggle('saved', added);
            button.setAttribute('aria-pressed', String(added));
            button.setAttribute('aria-label', label);
            button.title = label;
            $('.save-icon', button).textContent = added ? '♥' : '♡';
            if (added && motionAllowed()) $('.save-icon', button).animate(
                [{ transform: 'scale(.8)' }, { transform: 'scale(1.22)' }, { transform: 'scale(1)' }],
                { duration: 220 },
            );
            const text = $('.save-label', button);
            if (text) text.textContent = t(added ? 'Guardado' : 'Guardar noticia');
        }
        toast(added ? 'Noticia guardada' : 'Eliminada de guardados');
        if (location.pathname === '/guardados') loadSavedStories();
        return;
    }
    if (e.target.closest('#collect-btn')) { const btn = $('#collect-btn'); btn.disabled = true; btn.textContent = t('Consultando fuentes...'); try { const out = await api('/api/admin/collect', { method: 'POST' }); $('#collect-result').innerHTML = `<div class="notice">Leídas: ${out.fetched} · Nuevas: ${out.new} · Actualizadas: ${out.updated} · IA: ${out.ai}<br>${out.errors.length ? 'Advertencias: ' + safe(out.errors.slice(0, 3).join(' | ')) : 'Sin errores registrados'}</div>`; await hydrate(); loadPending(); } catch (ex) { toast(ex.message); } finally { btn.disabled = false; btn.textContent = t('↻ Ejecutar ronda ahora'); } return; }
    const rev = e.target.closest('[data-review]'); if (rev) { if (rev.dataset.review === 'approve' && !confirm(t('¿Revisaste la procedencia y las afirmaciones antes de aprobar?'))) return; try { await api('/api/admin/review/' + rev.dataset.newsId, { method: 'POST', body: JSON.stringify({ action: rev.dataset.review }) }); toast('Decisión editorial registrada'); await hydrate(); loadPending(); } catch (ex) { toast(ex.message); } return; }
}
async function submitForms(e) {
    const form = e.target;
    if (form.id === 'change-password-form') { e.preventDefault(); const data = Object.fromEntries(new FormData(form)); try { await api('/api/auth/change-password', { method: 'POST', body: JSON.stringify(data) }); form.reset(); toast('Contraseña actualizada'); } catch (ex) { toast(ex.message); } return; }
    if (form.id === 'delete-account-form') { e.preventDefault(); if (!confirm(t('Eliminarás tu cuenta y sus guardados asociados. ¿Continuar?'))) return; const data = Object.fromEntries(new FormData(form)); try { await api('/api/auth/delete-account', { method: 'POST', body: JSON.stringify(data) }); state.user = null; toast('Cuenta eliminada'); navigate('/'); } catch (ex) { toast(ex.message); } return; }
    if (form.id === 'auth-form') {
        e.preventDefault();
        const submit = $('button[type="submit"]', form);
        if (submit.disabled) return;
        const result = $('#auth-error', form);
        const label = submit.innerHTML;
        submit.disabled = true;
        submit.textContent = t('Un momento…');
        result.textContent = '';
        const data = Object.fromEntries(new FormData(form));
        try {
            state.user = await api('/api/auth/login', { method: 'POST', body: JSON.stringify(data) });
            toast('Acceso correcto');
            navigate(state.user.role === 'admin' ? '/admin' : '/cuenta');
        } catch (ex) {
            result.innerHTML = `<div class="error-note">${safe(translateMessage(ex.message))}</div>`;
        } finally {
            submit.innerHTML = label;
            submit.disabled = false;
        }
        return;
    }
    if (form.id === 'source-form') { e.preventDefault(); const data = Object.fromEntries(new FormData(form).entries()); try { await api('/api/admin/sources', { method: 'POST', body: JSON.stringify(data) }); state.sources = await api('/api/sources'); toast('RSS agregado correctamente'); render(); } catch (ex) { toast(ex.message); } return; }
}
function onSearch(e) {
    if (e.target.id !== 'radar-search') return;
    state.query = e.target.value.trim();
    radarPage = 1;
    $('#global-search').value = e.target.value;
    refreshFeed();
}
document.addEventListener('change', (event) => {
    const box = event.target.closest('[data-carousel-news]');
    if (!box) return;
    const id = Number(box.dataset.carouselNews);
    const current = new Set(state.carousel.selectedIds || []);
    if (box.checked) current.add(id); else current.delete(id);
    state.carousel.selectedIds = Array.from(current);
});
function bootEvents() {
    document.addEventListener('error', event => {
        const image = event.target;
        if (!image.matches?.('img[data-news-image]')) return;
        const photo = image.closest('.edition-photo');
        if (photo?.dataset.photoFallback) {
            image.src = photo.dataset.photoFallback;
            delete photo.dataset.photoFallback;
            return;
        }
        (image.closest('.small-art, .feed-art, .media-card, .edition-photo') || image).remove();
    }, true);
    document.addEventListener('click', e => { clickAction(e).catch(ex => toast(ex.message)); });
    document.addEventListener('submit', e => {
        if (e.target.id === 'global-search-form') {
            e.preventDefault();
            state.query = $('#global-search').value.trim();
            state.category = 'Todas';
            radarPage = 1;
            navigate('/radar');
            return;
        }
        submitForms(e).catch(ex => toast(ex.message));
    });
    document.addEventListener('input', onSearch);
    window.addEventListener('popstate', () => {
        toggleHeaderPanel('menu', false);
        toggleHeaderPanel('search', false);
        render();
    });
    document.addEventListener('keydown', e => {
        if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
            e.preventDefault();
            toggleHeaderPanel('menu', false);
            const localSearch = $('#radar-search');
            if (localSearch) localSearch.focus();
            else {
                toggleHeaderPanel('search', true);
                $('#global-search').focus();
            }
        }
        if (e.key !== 'Escape') return;
        for (const [panel, id] of [['menu', '#menu-button'], ['search', '#search-toggle']]) {
            const button = $(id);
            if (button.getAttribute('aria-expanded') !== 'true') continue;
            toggleHeaderPanel(panel, false);
            if (button.getClientRects().length) button.focus();
        }
    });
    document.addEventListener('visibilitychange', () => {
        if (!document.hidden && Date.now() - bootEvents.last > 15 * 60 * 1000) {
            hydrate().then(() => { bootEvents.last = Date.now(); render(); });
        }
    });
    bootEvents.last = Date.now();
}
async function fetchDirectStory() {
    const slug = location.pathname.match(/^\/noticias\/([^/]+)$/)?.[1];
    if (!slug || state.news.some(item => item.slug === slug) || state.top.some(item => item.slug === slug)) return;
    try { state.directStory = await api('/api/news/' + encodeURIComponent(slug)); }
    catch { state.directStory = null; }
}
function unavailableStory(story) {
    const open = ['es', 'en'].includes(story.language)
        ? `<button type="button" class="btn btn-dark" data-language="${story.language}">Abrir en su idioma original</button>`
        : '';
    return `<section class="container content-area"><h1>No se registra esta noticia en el idioma seleccionado.</h1>${open}</section>`;
}
(async function boot() {
    document.documentElement.lang = state.language;
    localize(document.body);
    initPreferences();
    bootEvents();
    await hydrate();
    await fetchDirectStory();
    render();
    cookieDialog();
})();
