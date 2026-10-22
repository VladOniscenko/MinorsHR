/*
 * Osiris minor-export (Hogeschool Rotterdam)
 *
 * Gebruik:
 *  1. Log in en open https://hr.osiris-student.nl/onderwijscatalogus, tabblad "Minors".
 *  2. Open de browserconsole (F12), plak dit script en druk op Enter.
 *  3. Klik daarna een filter (bijv. "Alleen open voor inschrijving") één keer aan of uit.
 *     Het script onderschept dan het zoekverzoek van de pagina, haalt ALLE minors op
 *     en downloadt osiris-export-<datum>.json (ook beschikbaar als window.__osirisExport).
 *  4. Zet het bestand in minor-tool/imports/ en voer uit:
 *       python tools/import_data.py osiris imports/osiris-export-<datum>.json
 *
 * Het script wijzigt niets in Osiris; het leest alleen de catalogus die je zelf mag zien.
 * Alleen opleidingen die met "B " (bachelor) of "Ad " beginnen worden bewaard.
 */
(() => {
  'use strict';
  const SEARCH = '/student/osiris/student/minoren_voor_owc/zoeken';
  const KEEP_STUDY = /^(B|Ad) /;
  const PAGE = 1000;

  if (window.__osirisHooked) { console.log('Hook staat al aan: klik een filter in Osiris aan of uit.'); return; }
  window.__osirisHooked = true;

  const origOpen = XMLHttpRequest.prototype.open;
  const origSend = XMLHttpRequest.prototype.send;
  const origSet = XMLHttpRequest.prototype.setRequestHeader;
  XMLHttpRequest.prototype.open = function (m, u) { this.__u = String(u); this.__h = {}; return origOpen.apply(this, arguments); };
  XMLHttpRequest.prototype.setRequestHeader = function (k, v) { (this.__h = this.__h || {})[k] = v; return origSet.apply(this, arguments); };
  XMLHttpRequest.prototype.send = function (b) {
    if (this.__u && this.__u.includes(SEARCH) && !window.__osirisCaptured) {
      window.__osirisCaptured = true;
      run(this.__u, this.__h, JSON.parse(b)).catch((e) => console.error('Export mislukt', e));
    }
    return origSend.apply(this, arguments);
  };

  const uniq = (a) => [...new Set(a)];
  const names = (a) => uniq((a || []).map((o) => o.opleiding_naam).filter((n) => KEEP_STUDY.test(n)));

  async function run(url, headers, tpl) {
    const hits = [];
    let total = Infinity;
    for (let from = 0; from < total; from += PAGE) {
      const body = { from, size: PAGE, sort: tpl.sort, query: { match_all: {} } };
      const res = await fetch(url, { method: 'POST', credentials: 'include', headers, body: JSON.stringify(body) });
      const json = await res.json();
      total = json.hits.total.value;
      hits.push(...json.hits.hits);
    }
    const items = hits.map((h) => h._source).filter((s) => (s.startmomenten_nested || []).length).map((s) => ({
      code: s.minor,
      name: s.minor_naam,
      programme: s.programma_naam || '',
      institute: s.faculteit_naam,
      ec: Number(s.punten),
      unit: s.punteneenheid,
      type: s.type_minor_omschrijving,
      intake_year: s.ingangsjaar,
      languages: (s.voertalen || []).map((v) => v.voertaal_omschrijving),
      starts: s.startmomenten_nested.map((m) => ({ year: m.collegejaar, block: m.blok, label: m.periode_omschrijving })),
      enrollment: (s.inschrijfperiodes || []).map((p) => ({ from: p.datum_vanaf, to: p.datum_tm })),
      target: names(s.opleidingen),
      admitted: names(s.ingangseisen),
    }));
    const out = {
      kind: 'osiris-minors', version: 1, retrieved: new Date().toISOString().slice(0, 10),
      source_url: location.origin + '/onderwijscatalogus', total_in_index: total, items,
    };
    window.__osirisExport = out;
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([JSON.stringify(out)], { type: 'application/json' }));
    a.download = `osiris-export-${out.retrieved}.json`;
    document.body.appendChild(a); a.click(); a.remove();
    console.log(`Klaar: ${items.length} minor-regels met startmoment (van ${total} in de index).`);
  }

  console.log('Hook actief. Klik nu een filter in Osiris aan of uit om de export te starten.');
})();
