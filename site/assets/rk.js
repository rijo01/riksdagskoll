/* Riksdagskoll — delad klientkod (vanilla JS, inga beroenden) */
(function () {
  'use strict';

  const RK = (window.RK = {});

  RK.PARTIER = ['S', 'SD', 'M', 'C', 'V', 'KD', 'MP', 'L'];
  RK.PARTINAMN = {
    S: 'Socialdemokraterna', SD: 'Sverigedemokraterna', M: 'Moderaterna',
    C: 'Centerpartiet', V: 'Vänsterpartiet', KD: 'Kristdemokraterna',
    MP: 'Miljöpartiet', L: 'Liberalerna', '-': 'Partilös',
  };
  RK.RMS = ['2022/23', '2023/24', '2024/25', '2025/26'];
  RK.VALDATUM = new Date('2026-09-13T08:00:00+02:00');
  RK.SEQ = ['#c6daf7', '#9fc0f0', '#74a3e6', '#4a85d9', '#2b67c4', '#1d4fa3', '#153b7d'];

  // ---------- Hjälpare ----------
  const cache = {};
  RK.data = async function (name) {
    if (!cache[name]) {
      cache[name] = fetch(RK.base() + 'data/' + name + '.json').then((r) => {
        if (!r.ok) throw new Error('Kunde inte läsa ' + name);
        return r.json();
      });
    }
    return cache[name];
  };
  // Bas-URL så att sidor i undermappar (t.ex. /ledamot/) hittar /data/
  RK.base = function () {
    return document.body.getAttribute('data-base') || '';
  };

  RK.fmt = function (n) {
    return (n == null) ? '–' : Number(n).toLocaleString('sv-SE');
  };
  RK.pct = function (n, dec) {
    if (n == null) return '–';
    return Number(n).toLocaleString('sv-SE', { minimumFractionDigits: dec == null ? 1 : dec, maximumFractionDigits: dec == null ? 1 : dec }) + ' %';
  };

  RK.el = function (tag, cls, text) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text; // alltid textContent — aldrig innerHTML för data
    return e;
  };

  RK.chip = function (parti) {
    const p = (parti === '-' || !parti) ? 'X' : parti;
    const c = RK.el('span', 'chip chip-' + p, parti === '-' ? '–' : parti);
    c.title = RK.PARTINAMN[parti] || 'Partilös';
    return c;
  };

  RK.rmShort = function (rm) { return rm.replace('/', ''); };

  // Sekventiell färg för andel 0–100 (samsyn)
  RK.seqColor = function (pct, min, max) {
    min = min == null ? 0 : min; max = max == null ? 100 : max;
    const t = Math.max(0, Math.min(1, (pct - min) / (max - min)));
    const i = Math.min(RK.SEQ.length - 1, Math.floor(t * RK.SEQ.length));
    return RK.SEQ[i];
  };
  RK.inkFor = function (hex) {
    const r = parseInt(hex.slice(1, 3), 16), g = parseInt(hex.slice(3, 5), 16), b = parseInt(hex.slice(5, 7), 16);
    const lum = (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255;
    return lum > 0.58 ? '#1c2430' : '#ffffff';
  };

  // ---------- Tooltip (en global; värdet först, etikett sekundär) ----------
  let tip;
  function ensureTip() {
    if (!tip) {
      tip = RK.el('div');
      tip.id = 'rk-tip';
      tip.setAttribute('role', 'status');
      document.body.appendChild(tip);
    }
    return tip;
  }
  RK.tipShow = function (evt, value, label) {
    const t = ensureTip();
    t.textContent = '';
    const v = RK.el('div', 't-v', value);
    t.appendChild(v);
    if (label) t.appendChild(RK.el('div', 't-l', label));
    t.classList.add('on');
    RK.tipMove(evt);
  };
  RK.tipMove = function (evt) {
    if (!tip) return;
    const pad = 14;
    let x = evt.clientX + pad, y = evt.clientY + pad;
    const r = tip.getBoundingClientRect();
    if (x + r.width > innerWidth - 8) x = evt.clientX - r.width - pad;
    if (y + r.height > innerHeight - 8) y = evt.clientY - r.height - pad;
    tip.style.left = x + 'px';
    tip.style.top = y + 'px';
  };
  RK.tipHide = function () { if (tip) tip.classList.remove('on'); };
  // Koppla tooltip till element (hover + tangentbordsfokus visar samma sak)
  RK.tipBind = function (el, getVL) {
    el.addEventListener('pointerenter', (e) => { const [v, l] = getVL(); RK.tipShow(e, v, l); });
    el.addEventListener('pointermove', RK.tipMove);
    el.addEventListener('pointerleave', RK.tipHide);
    el.tabIndex = el.tabIndex >= 0 ? el.tabIndex : 0;
    el.addEventListener('focus', () => {
      const [v, l] = getVL();
      const r = el.getBoundingClientRect();
      RK.tipShow({ clientX: r.left + r.width / 2, clientY: r.top }, v, l);
    });
    el.addEventListener('blur', RK.tipHide);
  };

  // ---------- Fördelningsstapel Ja/Nej/Avstår/Frånvarande ----------
  RK.fordelning = function (counts, opts) {
    // counts = [J, N, A, F]
    opts = opts || {};
    const namn = ['Ja', 'Nej', 'Avstår', 'Frånvarande'];
    const cls = ['f-ja', 'f-nej', 'f-avstar', 'f-franv'];
    const tot = counts.reduce((a, b) => a + b, 0) || 1;
    const wrap = RK.el('div', 'fordelning');
    wrap.setAttribute('role', 'img');
    wrap.setAttribute('aria-label', namn.map((n, i) => n + ': ' + counts[i]).join(', '));
    counts.forEach(function (c, i) {
      if (c <= 0) return;
      const s = RK.el('span', cls[i]);
      s.style.width = 'max(2px, calc(' + (100 * c / tot) + '% - 2px))';
      wrap.appendChild(s);
    });
    RK.tipBind(wrap, function () {
      return [
        namn.map((n, i) => counts[i] + ' ' + n.toLowerCase()).join(' · '),
        opts.label || 'Röstfördelning',
      ];
    });
    return wrap;
  };

  // ---------- Nedräkning ----------
  RK.nedrakning = function (el) {
    function tick() {
      const ms = RK.VALDATUM - new Date();
      if (ms <= 0) { el.textContent = 'Idag!'; return; }
      const d = Math.floor(ms / 86400000);
      el.textContent = d;
    }
    tick();
    setInterval(tick, 60000);
  };

  // ---------- Sidhuvud/na­vigering ----------
  RK.nav = function (aktiv) {
    const links = [
      ['index.html', 'Start', 'start'],
      ['ledamoter.html', 'Ledamöter', 'ledamoter'],
      ['voteringar.html', 'Voteringar', 'voteringar'],
      ['partikompassen.html', 'Partikompassen', 'partikompassen'],
      ['om.html', 'Om & metod', 'om'],
    ];
    const head = RK.el('header', 'site-head');
    const wrap = RK.el('div', 'wrap');
    const logo = RK.el('a', 'logo');
    logo.href = RK.base() + 'index.html';
    const sig = RK.el('span', 'sigill', 'R');
    logo.appendChild(sig);
    const lt = RK.el('span');
    const b = RK.el('b', null, 'Riksdags');
    const s = RK.el('span', null, 'koll');
    lt.appendChild(b); lt.appendChild(s);
    logo.appendChild(lt);
    wrap.appendChild(logo);
    const nav = RK.el('nav', 'main');
    nav.setAttribute('aria-label', 'Huvudmeny');
    links.forEach(function (l) {
      const a = RK.el('a', l[2] === aktiv ? 'on' : '', l[1]);
      a.href = RK.base() + l[0];
      nav.appendChild(a);
    });
    wrap.appendChild(nav);
    head.appendChild(wrap);
    document.body.prepend(head);
  };

  RK.foot = async function () {
    const f = RK.el('footer', 'site-foot');
    const w = RK.el('div', 'wrap');
    const c1 = RK.el('div');
    c1.appendChild(RK.el('div', 'brand', 'Riksdagskoll.se'));
    c1.appendChild(RK.el('div', null, 'Oberoende koll på hur riksdagen faktiskt röstar.'));
    const c2 = RK.el('div');
    const src = RK.el('div');
    src.appendChild(document.createTextNode('Data: '));
    const a = RK.el('a', null, 'Riksdagens öppna data');
    a.href = 'https://www.riksdagen.se/sv/dokument-och-lagar/riksdagens-oppna-data/';
    a.rel = 'noopener'; a.target = '_blank';
    src.appendChild(a);
    c2.appendChild(src);
    const gen = RK.el('div', null, 'Uppdaterad: läser …');
    c2.appendChild(gen);
    w.appendChild(c1); w.appendChild(c2);
    f.appendChild(w);
    document.body.appendChild(f);
    try {
      const meta = await RK.data('meta');
      gen.textContent = 'Uppdaterad: ' + (meta.genererad || '').slice(0, 10) + ' · Valet: 13 september 2026';
    } catch (e) {
      gen.textContent = 'Ingen data inläst ännu — se uppdatera.html';
    }
  };

  // ---------- Tabellväxel (diagram ↔ tabell, WCAG-tvilling) ----------
  RK.tabellToggle = function (container, chartEl, tableEl) {
    const btn = RK.el('button', 'btn btn-ghost tabell-toggle', 'Visa som tabell');
    btn.style.cssText = 'border-color:var(--line);color:var(--ink-2);padding:6px 12px;font-size:13px;';
    let table = false;
    btn.addEventListener('click', function () {
      table = !table;
      chartEl.hidden = table;
      tableEl.hidden = !table;
      btn.textContent = table ? 'Visa som diagram' : 'Visa som tabell';
    });
    tableEl.hidden = true;
    container.appendChild(btn);
  };
})();
