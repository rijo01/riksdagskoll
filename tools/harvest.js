/*
 * Riksdagskoll — datainsamlare ("harvester")
 * Körs i webbläsaren på https://data.riksdagen.se (same-origin fetch).
 * Används dels av Claude via Chrome-verktyg, dels av site/uppdatera.html.
 *
 * All data hämtas från Riksdagens öppna data (CC0-liknande villkor).
 * API-dokumentation: https://www.riksdagen.se/sv/dokument-och-lagar/riksdagens-oppna-data/
 */
(function () {
  const RMS = ['2022/23', '2023/24', '2024/25', '2025/26'];
  const PARTIER = ['S', 'M', 'SD', 'C', 'V', 'KD', 'L', 'MP', '-'];
  const BASE = 'https://data.riksdagen.se';

  const RK = (window.__RK = {
    state: 'idle',
    step: '',
    done: 0,
    total: 0,
    errors: [],
    samples: {},
    out: null,
    chunks: null,
  });

  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  function qs(params) {
    return Object.entries(params)
      .map(([k, v]) => encodeURIComponent(k) + '=' + encodeURIComponent(v))
      .join('&');
  }

  async function jget(path, params, retries) {
    retries = retries == null ? 3 : retries;
    const url = BASE + path + '?' + qs(params);
    for (let i = 0; i <= retries; i++) {
      try {
        const res = await fetch(url, { headers: { Accept: 'application/json' } });
        if (!res.ok) throw new Error('HTTP ' + res.status);
        const txt = await res.text();
        const data = JSON.parse(txt);
        RK.done++;
        return data;
      } catch (e) {
        if (i === retries) {
          RK.errors.push(url + ' :: ' + e.message);
          RK.done++;
          return null;
        }
        await sleep(600 * (i + 1));
      }
    }
  }

  // Normalisera: fält kan vara objekt (1 träff) eller array (flera)
  function arr(x) {
    if (x == null) return [];
    return Array.isArray(x) ? x : [x];
  }

  // voteringlista-svar: { voteringlista: { '@antal': 'N', votering: [...] } }
  async function vlista(params) {
    const data = await jget('/voteringlista/', Object.assign({ utformat: 'json' }, params));
    if (!data) return [];
    const top = data.voteringlista || data;
    return arr(top.votering);
  }

  const N = (x) => parseInt(x, 10) || 0;

  // Kör många uppgifter med begränsad samtidighet
  async function pool(tasks, conc, spacingMs) {
    const results = new Array(tasks.length);
    let idx = 0;
    async function worker() {
      while (idx < tasks.length) {
        const my = idx++;
        results[my] = await tasks[my]();
        if (spacingMs) await sleep(spacingMs);
      }
    }
    await Promise.all(Array.from({ length: conc }, worker));
    return results;
  }

  // ---- Steg 1: Ledamöter ----
  async function fetchLedamoter() {
    RK.step = 'ledamöter';
    const data = await jget('/personlista/', { utformat: 'json' });
    const personer = arr(data && data.personlista && data.personlista.person);
    if (personer[0]) RK.samples.person = Object.keys(personer[0]);
    return personer.map((p) => ({
      iid: p.intressent_id,
      fn: p.tilltalsnamn,
      en: p.efternamn,
      parti: (p.parti || '-').toUpperCase(),
      valkrets: p.valkrets || '',
      kon: p.kon || '',
      fodd: p.fodd_ar || '',
      bild: p.bild_url_192 || p.bild_url_80 || '',
      status: p.status || '',
    }));
  }

  // ---- Steg 2: Närvaro per ledamot och riksmöte ----
  async function fetchNarvaro() {
    RK.step = 'närvaro';
    const out = {};
    for (const rm of RMS) {
      const rows = await vlista({ rm: rm, gruppering: 'ledamot_id', sz: 10000 });
      if (rows[0] && !RK.samples.narvaro) RK.samples.narvaro = Object.keys(rows[0]);
      out[rm] = rows.map((r) => ({
        iid: r.intressent_id || r.iid || r.ledamot_id || '',
        namn: r.namn || ((r.fornamn || '') + ' ' + (r.efternamn || '')).trim(),
        parti: (r.parti || '-').toUpperCase(),
        valkrets: r.valkrets || '',
        J: N(r.Ja), Nj: N(r.Nej), A: N(r['Avstår'] != null ? r['Avstår'] : r.Avstar), F: N(r['Frånvarande'] != null ? r['Frånvarande'] : r.Franvarande),
      }));
    }
    return out;
  }

  // ---- Steg 3+4: Voteringar med total- och partiutfall ----
  async function fetchVoteringar() {
    RK.step = 'voteringar';
    const out = {}; // rm -> key(bet|punkt) -> {bet,punkt,tot,parti:{}}
    for (const rm of RMS) out[rm] = {};

    const tasks = [];
    for (const rm of RMS) {
      tasks.push(async () => {
        const rows = await vlista({ rm: rm, gruppering: 'votering_bet_punkt', sz: 10000 });
        if (rows[0] && !RK.samples.votTot) RK.samples.votTot = Object.keys(rows[0]);
        for (const r of rows) {
          const bet = r.beteckning || r.bet || '';
          const punkt = r.punkt != null ? String(r.punkt) : '';
          const key = bet + '|' + punkt;
          const cur = out[rm][key] || (out[rm][key] = { bet: bet, punkt: punkt, parti: {} });
          cur.tot = [N(r.Ja), N(r.Nej), N(r['Avstår']), N(r['Frånvarande'])];
          if (r.votering_id) cur.vid = r.votering_id;
          if (r.systemdatum || r.datum) cur.datum = String(r.systemdatum || r.datum).slice(0, 10);
          if (r.avser || r.rubrik || r.titel) cur.avser = r.avser || r.rubrik || r.titel;
        }
      });
      for (const p of PARTIER) {
        tasks.push(async () => {
          const rows = await vlista({ rm: rm, parti: p, gruppering: 'votering_bet_punkt', sz: 10000 });
          for (const r of rows) {
            const bet = r.beteckning || r.bet || '';
            const punkt = r.punkt != null ? String(r.punkt) : '';
            const key = bet + '|' + punkt;
            const cur = out[rm][key] || (out[rm][key] = { bet: bet, punkt: punkt, parti: {} });
            cur.parti[p] = [N(r.Ja), N(r.Nej), N(r['Avstår']), N(r['Frånvarande'])];
          }
        });
      }
    }
    RK.total += tasks.length;
    await pool(tasks, 3, 120);
    return out;
  }

  // ---- Steg 5: Betänkandetitlar ----
  async function fetchBetTitlar() {
    RK.step = 'betänkanden';
    const out = {}; // rm -> bet -> {titel, datum, organ}
    for (const rm of RMS) {
      out[rm] = {};
      let p = 1;
      for (;;) {
        const data = await jget('/dokumentlista/', {
          doktyp: 'bet', rm: rm, utformat: 'json', sz: 200, p: p, sort: 'datum', sortorder: 'asc',
        });
        const dl = data && data.dokumentlista;
        const docs = arr(dl && dl.dokument);
        if (docs[0] && !RK.samples.bet) RK.samples.bet = Object.keys(docs[0]);
        for (const d of docs) {
          const bet = (d.beteckning || '').toUpperCase();
          if (bet) out[rm][bet] = { titel: d.titel || '', datum: (d.datum || '').slice(0, 10), organ: d.organ || '' };
        }
        const sidor = N(dl && dl['@sidor']);
        if (!docs.length || p >= sidor) break;
        p++;
        await sleep(120);
      }
    }
    return out;
  }

  // ---- Steg 6: Rebeller (avvikande röster där partiet splittrats) ----
  function findSplits(voteringar) {
    const splits = [];
    for (const rm of RMS) {
      const vv = voteringar[rm] || {};
      for (const key of Object.keys(vv)) {
        const v = vv[key];
        for (const p of Object.keys(v.parti)) {
          const c = v.parti[p]; // [J,N,A,F]
          if (!c) continue;
          const j = c[0], n = c[1];
          if (j > 0 && n > 0) {
            const minority = j < n ? 'ja' : n < j ? 'nej' : null;
            if (minority) {
              splits.push({ rm: rm, bet: v.bet, punkt: v.punkt, parti: p, rost: minority, antal: Math.min(j, n), majJ: j, majN: n });
            }
          }
        }
      }
    }
    return splits;
  }

  async function fetchRebeller(splits) {
    RK.step = 'rebeller (' + splits.length + ' splittringar)';
    RK.total += splits.length;
    const events = [];
    const tasks = splits.map((s) => async () => {
      const rows = await vlista({ rm: s.rm, bet: s.bet, punkt: s.punkt, parti: s.parti, rost: s.rost, sz: 500 });
      if (rows[0] && !RK.samples.rebell) RK.samples.rebell = Object.keys(rows[0]);
      for (const r of rows) {
        events.push({
          rm: s.rm, bet: s.bet, punkt: s.punkt, parti: s.parti,
          rost: s.rost === 'ja' ? 'Ja' : 'Nej',
          iid: r.intressent_id || '',
          namn: r.namn || ((r.fornamn || '') + ' ' + (r.efternamn || '')).trim(),
          valkrets: r.valkrets || '',
          datum: String(r.systemdatum || r.datum || '').slice(0, 10),
          vid: r.votering_id || '',
          majJ: s.majJ, majN: s.majN,
        });
      }
    });
    await pool(tasks, 3, 100);
    return events;
  }

  // ---- Export: gzip + base64, chunkat ----
  async function pack(obj, chunkSize) {
    chunkSize = chunkSize || 100000;
    const json = JSON.stringify(obj);
    const stream = new Blob([json]).stream().pipeThrough(new CompressionStream('gzip'));
    const buf = await new Response(stream).arrayBuffer();
    const bytes = new Uint8Array(buf);
    let bin = '';
    const B = 0x8000;
    for (let i = 0; i < bytes.length; i += B) {
      bin += String.fromCharCode.apply(null, bytes.subarray(i, i + B));
    }
    const b64 = btoa(bin);
    const chunks = [];
    for (let i = 0; i < b64.length; i += chunkSize) chunks.push(b64.slice(i, i + chunkSize));
    RK.chunks = chunks;
    return { chunks: chunks.length, jsonBytes: json.length, gzB64Bytes: b64.length };
  }

  // ---- Huvudflöde ----
  RK.run = async function () {
    RK.state = 'running';
    RK.errors = [];
    RK.done = 0;
    RK.total = 1 + RMS.length + RMS.length * (1 + PARTIER.length) + RMS.length; // grovt; rebeller läggs på
    try {
      const ledamoter = await fetchLedamoter();
      const narvaro = await fetchNarvaro();
      const voteringar = await fetchVoteringar();
      const betTitlar = await fetchBetTitlar();
      const splits = findSplits(voteringar);
      const rebeller = await fetchRebeller(splits);
      RK.out = {
        version: 1,
        rms: RMS,
        partier: PARTIER,
        ledamoter: ledamoter,
        narvaro: narvaro,
        voteringar: voteringar,
        betTitlar: betTitlar,
        rebeller: rebeller,
      };
      RK.state = 'done';
      RK.step = 'klart';
      return { ok: true, ledamoter: ledamoter.length, splits: splits.length, rebeller: rebeller.length, errors: RK.errors.length };
    } catch (e) {
      RK.state = 'error';
      RK.errors.push('FATAL: ' + (e && e.message));
      return { ok: false, error: String(e) };
    }
  };

  RK.pack = pack;
  RK.status = function () {
    return { state: RK.state, step: RK.step, done: RK.done, total: RK.total, errors: RK.errors.slice(0, 5), errorCount: RK.errors.length, samples: RK.samples };
  };
})();
