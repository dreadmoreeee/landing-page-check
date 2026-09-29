"""JavaScript evaluated in the page after load. Read-only: it never clicks,
scrolls or types. Returns plain JSON-serialisable facts; all judgement
happens in Python (analysis.py)."""

DOM_SCRIPT = r"""
() => {
  const W = window.innerWidth, H = window.innerHeight;
  const docW = Math.max(document.documentElement.scrollWidth, W);
  const norm = s => (s || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '')
    .toLowerCase().replace(/\s+/g, ' ').trim();

  const clipped = (el, r) => {
    for (let n = el.parentElement; n && n !== document.body && n !== document.documentElement; n = n.parentElement) {
      const s = getComputedStyle(n);
      if (s.overflowX !== 'visible' || s.overflowY !== 'visible') {
        const p = n.getBoundingClientRect();
        if (r.right <= p.left || r.left >= p.right || r.bottom <= p.top || r.top >= p.bottom) return true;
      }
      if (s.position === 'fixed') break;
    }
    return false;
  };
  const isVisible = el => {
    if (!el || el.nodeType !== 1) return false;
    const r = el.getBoundingClientRect();
    if (r.width <= 2 || r.height <= 2) return false;
    if (r.right <= 0 || r.bottom <= 0 || r.left >= docW) return false;
    if (el.checkVisibility) {
      if (!el.checkVisibility({opacityProperty: true, visibilityProperty: true})) return false;
    } else {
      for (let n = el; n && n.nodeType === 1; n = n.parentElement) {
        const s = getComputedStyle(n);
        if (s.display === 'none' || parseFloat(s.opacity) === 0) return false;
      }
      if (getComputedStyle(el).visibility !== 'visible') return false;
    }
    return !clipped(el, r);
  };
  const visibleDeep = el => {
    if (isVisible(el)) return true;
    if (el.shadowRoot) {
      for (const c of el.shadowRoot.querySelectorAll('*')) if (isVisible(c)) return true;
    }
    return false;
  };
  const inView = r => r.top < H && r.bottom > 0 && r.left < W && r.right > 0;
  const inFold = r => inView(r) && (r.top + r.height / 2) < H;
  const label = el => {
    let t = (el.innerText || '').replace(/\s+/g, ' ').trim();
    if (!t && el.tagName === 'INPUT') t = (el.value || '').trim();
    if (!t) t = (el.getAttribute('aria-label') || el.getAttribute('title') || '').trim();
    if (!t && el.querySelector) {
      const img = el.querySelector('img[alt]');
      if (img) t = img.getAttribute('alt').trim();
    }
    return t.slice(0, 60);
  };
  const desc = el => {
    if (!el || !el.tagName) return '';
    let d = el.tagName.toLowerCase();
    if (el.id) d += '#' + el.id;
    else if (typeof el.className === 'string' && el.className.trim())
      d += '.' + el.className.trim().split(/\s+/).slice(0, 2).join('.');
    return d.slice(0, 80);
  };
  const box = r => ({x: Math.round(r.left), y: Math.round(r.top), w: Math.round(r.width), h: Math.round(r.height)});

  // ---- consent banner (looked up first so its buttons are not taken as CTAs)
  const CMP = ['#onetrust-banner-sdk', '#onetrust-consent-sdk', '#CybotCookiebotDialog', '#didomi-host',
    '#didomi-notice', '#axeptio_overlay', '#tarteaucitronRoot', '#tarteaucitronAlertBig', '#usercentrics-root',
    '#uc-banner', '.cc-window', '.cc-banner', '#cookie-law-info-bar', '.cmplz-cookiebanner', '#cookie-notice',
    '#cookieConsent', '#qc-cmp2-container', '.fc-consent-root', '#iubenda-cs-banner', '#cky-consent',
    '.cky-consent-container', '#moove_gdpr_cookie_info_bar', '#BorlabsCookieBox', '#cmpbox', '.osano-cm-dialog'];
  let bannerEl = null, bannerHow = null;
  for (const sel of CMP) {
    for (const el of document.querySelectorAll(sel)) {
      if (visibleDeep(el)) { bannerEl = el; bannerHow = sel; break; }
    }
    if (bannerEl) break;
  }
  const all = Array.from(document.querySelectorAll('body *'));
  if (!bannerEl) {
    const words = /(cookie|temoin|consent|gdpr|rgpd|loi 25|traceur)/;
    for (const el of all) {
      const s = getComputedStyle(el);
      const role = el.getAttribute('role');
      const modal = s.position === 'fixed' || s.position === 'sticky' || role === 'dialog' ||
        role === 'alertdialog' || el.getAttribute('aria-modal') === 'true' || el.tagName === 'DIALOG';
      const named = /(cookie|consent|gdpr|rgpd)/i.test((el.id || '') + ' ' + (typeof el.className === 'string' ? el.className : ''));
      if (!modal && !named) continue;
      if (!isVisible(el)) continue;
      const r = el.getBoundingClientRect();
      if (!inView(r) || r.height < 30) continue;
      if (words.test(norm(el.innerText).slice(0, 3000))) { bannerEl = el; bannerHow = 'text'; break; }
    }
  }
  const banner = bannerEl ? {
    visible: true, element: desc(bannerEl), matched: bannerHow,
    text: (bannerEl.innerText || '').replace(/\s+/g, ' ').trim().slice(0, 160),
    box: box(bannerEl.getBoundingClientRect())
  } : {visible: false};

  // ---- head facts
  const metaRobots = Array.from(document.querySelectorAll('meta[name]'))
    .filter(m => ['robots', 'googlebot'].includes((m.getAttribute('name') || '').toLowerCase()))
    .map(m => ({name: m.getAttribute('name').toLowerCase(), content: m.getAttribute('content') || ''}));
  const canonicals = Array.from(document.querySelectorAll('link[rel~="canonical" i]')).map(l => l.href || l.getAttribute('href'));
  const h1All = Array.from(document.querySelectorAll('h1'));
  const h1 = h1All.filter(isVisible).map(e => (e.innerText || '').replace(/\s+/g, ' ').trim()).filter(Boolean);

  // ---- above-the-fold text
  const parts = [];
  let total = 0;
  const walker = document.createTreeWalker(document.body || document.documentElement, NodeFilter.SHOW_TEXT);
  const range = document.createRange();
  for (let n = walker.nextNode(); n && total < 6000; n = walker.nextNode()) {
    const t = n.nodeValue.replace(/\s+/g, ' ').trim();
    if (!t) continue;
    const p = n.parentElement;
    if (!p || ['SCRIPT', 'STYLE', 'NOSCRIPT', 'TEMPLATE'].includes(p.tagName)) continue;
    range.selectNodeContents(n);
    const rects = Array.from(range.getClientRects());
    if (!rects.some(r => r.width > 0 && r.height > 0 && inView(r))) continue;
    if (!isVisible(p)) continue;
    parts.push(t);
    total += t.length + 1;
  }

  // ---- first-screen calls to action
  const CTA_RE = /\b(contact|quote|estimate|book|call|get started|start now|sign up|signup|subscribe|buy|order|shop|request|schedule|apply|download|free|demo|trial|consult|hire|talk|chat|join|register|devis|soumission|reserv|appel|commenc|command|achet|essai|demande|inscri|obten|telecharg|rendez|joindre|ecriv|parlons|discutons|planifi)/;
  const NOT_CTA = /\b(menu|navigation|toggle|close|fermer|search|recherche|language|langue|previous|next|precedent|suivant|slide|play|pause|mute|cookie|accept|reject|refuse|accepter|refuser|settings|parametres|preferences|dismiss|skip)\b/;
  const ctas = [];
  const inBanner = el => bannerEl && bannerEl.contains(el);
  const coveredBy = (el, r) => {
    const cx = Math.min(Math.max(r.left + r.width / 2, 0), W - 1);
    const cy = Math.min(Math.max(r.top + r.height / 2, 0), H - 1);
    const hit = document.elementFromPoint(cx, cy);
    if (!hit || hit === el || el.contains(hit) || hit.contains(el)) return null;
    return desc(hit);
  };
  for (const el of document.querySelectorAll('a[href], button, input[type=submit], input[type=button], input[type=image], [role=button]')) {
    if (inBanner(el) || !isVisible(el)) continue;
    const r = el.getBoundingClientRect();
    if (!inFold(r)) continue;
    const href = (el.getAttribute('href') || '').trim().toLowerCase();
    const text = norm(label(el));
    let kind = null;
    if (href.startsWith('tel:')) kind = 'tel';
    else if (!text || NOT_CTA.test(text)) continue;
    else if (el.tagName === 'A') {
      const cls = norm(typeof el.className === 'string' ? el.className : '');
      if (CTA_RE.test(text) || /(^|[\s_-])(btn|button|cta)/.test(cls) || el.getAttribute('role') === 'button') kind = 'link';
    } else kind = 'button';
    if (!kind) continue;
    ctas.push({kind, text: label(el), element: desc(el), href: el.href || null, box: box(r), covered_by: coveredBy(el, r)});
  }

  // ---- forms
  const FIELD_SEL = 'input:not([type=hidden]):not([type=submit]):not([type=button]):not([type=reset]):not([type=image]), select, textarea';
  const fieldInfo = fields => {
    const groups = new Map();
    fields.forEach((f, i) => {
      if (!isVisible(f)) return;
      const t = (f.getAttribute('type') || '').toLowerCase();
      const key = (t === 'radio' || t === 'checkbox') && f.name ? t + ':' + f.name : 'f' + i;
      const req = f.required || f.getAttribute('aria-required') === 'true';
      const g = groups.get(key) || {req: false, name: f.getAttribute('name') || f.getAttribute('placeholder') || f.id || t || f.tagName.toLowerCase(), type: t || f.tagName.toLowerCase()};
      g.req = g.req || req;
      groups.set(key, g);
    });
    return Array.from(groups.values());
  };
  const forms = [];
  for (const f of document.querySelectorAll('form')) {
    if ((f.getAttribute('role') || '') === 'search') continue;
    const fs = fieldInfo(Array.from(f.querySelectorAll(FIELD_SEL)));
    if (!fs.length) continue;
    if (fs.every(g => g.type === 'search' || ['q', 's', 'search'].includes((g.name || '').toLowerCase()))) continue;
    const vis = Array.from(f.querySelectorAll(FIELD_SEL)).filter(isVisible);
    const atf = vis.some(x => inFold(x.getBoundingClientRect()));
    forms.push({element: desc(f), fields: fs.length, required: fs.filter(g => g.req).length,
      names: fs.map(g => g.name).slice(0, 12), above_fold: atf, box: box(f.getBoundingClientRect())});
    if (atf && !inBanner(f)) ctas.push({kind: 'form', text: fs.length + ' field(s)', element: desc(f), href: null,
      box: box(vis[0].getBoundingClientRect()), covered_by: coveredBy(vis[0], vis[0].getBoundingClientRect())});
  }
  const orphan = Array.from(document.querySelectorAll(FIELD_SEL)).filter(f => !f.closest('form') && !inBanner(f));
  const og = fieldInfo(orphan).filter(g => g.type !== 'search');
  if (og.length) forms.push({element: '(fields outside a form element)', fields: og.length,
    required: og.filter(g => g.req).length, names: og.map(g => g.name).slice(0, 12), above_fold: false, box: null});

  // ---- tap targets
  const TAP_SEL = 'a[href], button, input:not([type=hidden]), select, textarea, [role=button], [role=link], [role=checkbox], [role=tab], [onclick], summary';
  let cands = Array.from(document.querySelectorAll(TAP_SEL)).filter(isVisible);
  const candSet = new Set(cands);
  cands = cands.filter(el => { for (let p = el.parentElement; p; p = p.parentElement) if (candSet.has(p)) return false; return true; });
  let inlineSkipped = 0;
  const targets = [];
  for (const el of cands) {
    if (el.tagName === 'A' && getComputedStyle(el).display === 'inline') {
      let b = el.parentElement;
      while (b && getComputedStyle(b).display === 'inline') b = b.parentElement;
      const own = (el.innerText || '').trim().length;
      if (b && (b.innerText || '').trim().length > own + 20) { inlineSkipped++; continue; }
    }
    targets.push({el, r: el.getBoundingClientRect()});
    if (targets.length >= 800) break;
  }
  const small = [];
  let crowded = 0;
  for (const t of targets) {
    const r = t.r;
    if (r.width >= 47.5 && r.height >= 47.5) continue;
    const cx = r.left + r.width / 2, cy = r.top + r.height / 2;
    const z = {left: cx - 24, right: cx + 24, top: cy - 24, bottom: cy + 24};
    let near = null;
    for (const o of targets) {
      if (o === t) continue;
      const q = o.r;
      if (q.left < z.right && q.right > z.left && q.top < z.bottom && q.bottom > z.top) { near = o; break; }
    }
    if (near) crowded++;
    small.push({element: desc(t.el), text: label(t.el), w: Math.round(r.width), h: Math.round(r.height),
      near: near ? (label(near.el) || desc(near.el)) : null});
  }
  small.sort((a, b) => (b.near ? 1 : 0) - (a.near ? 1 : 0) || (a.w * a.h) - (b.w * b.h));

  // ---- phone links, trust
  const tel = Array.from(document.querySelectorAll('a[href]'))
    .filter(a => (a.getAttribute('href') || '').trim().toLowerCase().startsWith('tel:'))
    .map(a => ({href: a.getAttribute('href').trim(), text: label(a), visible: isVisible(a),
      above_fold: isVisible(a) && inFold(a.getBoundingClientRect())}));
  const PRIV = /(privacy|privacite|confidentialit|vie privee|vie-privee|datenschutz|privacidad)/;
  const privacy = Array.from(document.querySelectorAll('a[href]'))
    .filter(a => PRIV.test(norm((a.getAttribute('href') || '') + ' ' + (a.innerText || a.textContent || ''))))
    .map(a => ({href: a.href, text: label(a) || (a.textContent || '').trim().slice(0, 60)})).slice(0, 5);
  const jsonld = Array.from(document.querySelectorAll('script[type="application/ld+json" i]')).map(s => s.textContent).slice(0, 30);
  const microdata = Array.from(document.querySelectorAll('[itemtype]')).map(e => e.getAttribute('itemtype')).slice(0, 100);
  const addressEls = Array.from(document.querySelectorAll('address')).filter(isVisible)
    .map(e => (e.innerText || '').replace(/\s+/g, ' ').trim().slice(0, 200));
  const vp = document.querySelector('meta[name="viewport" i]');

  return {
    viewport: {w: W, h: H}, title: document.title || '', lang: document.documentElement.lang || '',
    meta_viewport: vp ? vp.getAttribute('content') : null,
    meta_robots: metaRobots, canonicals, h1, h1_hidden: h1All.length - h1.length,
    atf_text: parts.join(' ').slice(0, 6000),
    body_text: (document.body ? document.body.innerText : '').slice(0, 300000),
    ctas, forms, consent_banner: banner,
    tap: {total: targets.length, inline_links_skipped: inlineSkipped, small: small.length, crowded, examples: small.slice(0, 8)},
    tel_links: tel, privacy_links: privacy, jsonld, microdata, address_elements: addressEls
  };
}
"""

LCP_SCRIPT = r"""
() => new Promise(resolve => {
  let last = null;
  const done = () => {
    const nav = performance.getEntriesByType('navigation')[0];
    resolve({
      lcp: last ? {ms: Math.round(last.startTime), size: last.size,
        element: last.element ? (last.element.tagName.toLowerCase() + (last.element.id ? '#' + last.element.id : '')) : null,
        url: last.url || null} : null,
      nav: nav ? {ttfb_ms: Math.round(nav.responseStart), dcl_ms: Math.round(nav.domContentLoadedEventEnd),
        load_ms: Math.round(nav.loadEventEnd)} : null
    });
  };
  try {
    const po = new PerformanceObserver(list => {
      const es = list.getEntries();
      if (es.length) last = es[es.length - 1];
    });
    po.observe({type: 'largest-contentful-paint', buffered: true});
    setTimeout(() => { po.disconnect(); done(); }, 300);
  } catch (e) { done(); }
})
"""
