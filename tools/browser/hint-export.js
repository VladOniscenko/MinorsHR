/*
 * HINT minor-export (Hogeschool Rotterdam)
 *
 * Gebruik (ingelogd op https://hint.hr.nl/nl/HR/Studie/keuzes-in-je-studie/Minors/Minoroverzicht/):
 *  1. Plak dit script in de browserconsole (F12) en druk op Enter. Het verzamelt de minors van het
 *     tabblad dat je ziet (Voltijd, Deeltijd of Duaal) en bewaart ze in sessionStorage.
 *  2. Ga naar het volgende tabblad (de pagina herlaadt), plak het script opnieuw. Herhaal voor alle tabbladen.
 *  3. Roep daarna aan:  await hintDownload()
 *     Optioneel extra pagina's (bijv. RBS-programma's, die niet in het overzicht staan):
 *       await hintDownload(['https://hint.hr.nl/nl/Instituten/RBS/.../Omgaan-met-AI-OMA/'])
 *     Het script leest elke minorpagina en downloadt hint-export-<datum>.json (ook window.__hintExport).
 *  4. Zet het bestand in minor-tool/imports/ en voer uit:
 *       python tools/import_data.py hint imports/hint-export-<datum>.json --year 2026-2027
 *
 * Het script leest alleen pagina's die je zelf mag zien. Persoonsgegevens (coördinatoren) worden niet bewaard.
 */
(() => {
  'use strict';
  const KEY = 'hint-export-links';
  const CONCURRENCY = 6;
  const MAX_TEXT = 14000;

  const saved = JSON.parse(sessionStorage.getItem(KEY) || '{}');
  const tab = ((location.hash.match(/MinorTab=(\w+)/) || [])[1]) || 'Voltijd';
  document.querySelectorAll('li a[href*="/link/"]').forEach((a) => {
    const href = a.getAttribute('href').replace(/\?.*$/, '');
    const name = (a.innerText || '').split('\n')[0].trim();
    const e = saved[href] || (saved[href] = { name, tabs: [] });
    if (!e.tabs.includes(tab)) e.tabs.push(tab);
  });
  sessionStorage.setItem(KEY, JSON.stringify(saved));
  console.log(`Tabblad ${tab} verzameld. In totaal ${Object.keys(saved).length} minors. Herhaal voor andere tabbladen of roep: await hintDownload()`);

  const clean = (t) => t.replace(/[ \t\r]+/g, ' ').replace(/\s*\n\s*/g, '\n').replace(/\n{2,}/g, '\n').trim();

  async function fetchPage(url) {
    const res = await fetch(url, { credentials: 'include' });
    const html = await res.text();
    const doc = new DOMParser().parseFromString(html, 'text/html');
    const h1 = doc.querySelector('h1');
    if (!h1) return { url: res.url, status: res.status, name: '', text: '' };
    // dt/dd-blokken (Locatie, Studiepunten, ...) en de verborgen panelen (Toelatingseisen, Achtergrondinformatie) staan in de HTML
    const root = (h1.closest('div[class]') && h1.closest('div[class]').parentElement && h1.closest('div[class]').parentElement.parentElement) || doc.body;
    root.querySelectorAll('a[href^="mailto:"]').forEach((a) => a.remove());
    // zonder layout ontbreken regeleinden tussen blokelementen; voeg ze toe
    root.querySelectorAll('p,div,li,ul,ol,h1,h2,h3,h4,h5,h6,dt,dd,tr,br,section,article,table').forEach((e) => e.insertAdjacentText('afterend', '\n'));
    return { url: res.url, status: res.status, name: h1.textContent.trim(), text: clean(root.textContent).slice(0, MAX_TEXT) };
  }

  window.hintDownload = async (extraUrls = []) => {
    const links = JSON.parse(sessionStorage.getItem(KEY) || '{}');
    const jobs = Object.entries(links).map(([href, v]) => ({ link: href, listName: v.name, tabs: v.tabs, url: href }));
    extraUrls.forEach((u) => jobs.push({ link: u, listName: '', tabs: [], url: u }));
    const items = [];
    let next = 0;
    const worker = async () => {
      while (next < jobs.length) {
        const j = jobs[next++];
        try { items.push({ ...j, ...(await fetchPage(j.url)) }); } catch (e) { items.push({ ...j, error: String(e) }); }
      }
    };
    await Promise.all(Array.from({ length: CONCURRENCY }, worker));
    const out = { kind: 'hint-minors', version: 1, retrieved: new Date().toISOString().slice(0, 10), source_url: location.href.split('#')[0], items };
    window.__hintExport = out;
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([JSON.stringify(out)], { type: 'application/json' }));
    a.download = `hint-export-${out.retrieved}.json`;
    document.body.appendChild(a); a.click(); a.remove();
    console.log(`Klaar: ${items.length} pagina's.`);
    return out;
  };
})();
