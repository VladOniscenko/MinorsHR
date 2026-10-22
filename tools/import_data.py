#!/usr/bin/env python3
"""Importeert exports uit Osiris en HINT in de dataset (minor-tool/data/*.json).

Gebruik:
    python tools/import_data.py osiris imports/osiris-export-2026-10-22.json
    python tools/import_data.py hint   imports/hint-export-2026-10-22.json --year 2026-2027

Het importeren is idempotent: opnieuw importeren werkt bestaande records bij in plaats van te dupliceren.
Handmatig onderhouden gegevens (beoordelingen, kalender, programma's) blijven onaangeroerd.
"""
import argparse
import datetime as dt
import json
import os
import re
import sys
import unicodedata
from pathlib import Path

DATA = Path(os.environ.get('MINOR_TOOL_DATA') or Path(__file__).resolve().parent.parent / 'data')
TERM = {'SEM-N': 'N', 'SEM-V': 'V'}
LANG = {'nederlands': 'NL', 'engels': 'EN', 'duits': 'DE', 'frans': 'FR'}


# ---------- helpers ----------
def load(name, default):
    p = DATA / name
    return json.loads(p.read_text(encoding='utf-8')) if p.exists() else default


def save(name, obj):
    (DATA / name).write_text(json.dumps(obj, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')


def slug(s):
    s = unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode()
    return re.sub(r'[^a-z0-9]+', '-', s.lower()).strip('-')


def norm(s):
    return re.sub(r'[^a-z0-9]', '', unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode().lower())


def loose(s):
    s = s.lower().replace('*', ' ')
    s = re.sub(r'\((vt|dt|du|dt/du|vt stageroute)\)', '', s)
    s = re.sub(r',\s*(vt|dt)\b', '', s)
    s = re.sub(r'\s+(vt|dt|du)$', '', s)
    return norm(s)


def amsterdam_date(iso):
    """'2026-12-01T22:59:00Z' -> '2026-12-01' (lokale datum in Nederland)."""
    d = dt.datetime.strptime(iso[:19], '%Y-%m-%dT%H:%M:%S').replace(tzinfo=dt.timezone.utc)
    try:
        from zoneinfo import ZoneInfo
        return d.astimezone(ZoneInfo('Europe/Amsterdam')).date().isoformat()
    except Exception:
        return (d + dt.timedelta(hours=1 if d.month in (11, 12, 1, 2, 3) else 2)).date().isoformat()


class Store:
    def __init__(self):
        self.studies = load('studies.json', [])
        self.minors = load('minors.json', [])
        self.offerings = load('offerings.json', [])
        self.institutes = load('institutes.json', [])
        self.calendar = load('calendar.json', {})
        self.sources = load('sources.json', {'sources': [], 'snapshots': []})
        self.study_by_name = {s['name']: s for s in self.studies}
        self.minor_by_id = {m['id']: m for m in self.minors}
        self.off_by_id = {o['id']: o for o in self.offerings}
        self.aliases = {norm(a): mid for mid, al in load('aliases.json', {}).items() for a in al}

    # --- instituten ---
    def inst_code(self, name):
        n = (name or '').lower()
        for i in self.institutes:
            if any(k in n for k in i.get('match', [])):
                return i['code']
        if not name:
            return ''
        code = ''.join(w[0] for w in re.findall(r'[A-Za-z]+', name) if w[0].isupper())[:4] or slug(name)[:4].upper()
        self.institutes.append({'code': code, 'name': name, 'match': [n]})
        print(f'  nieuw instituut: {code} = {name}')
        return code

    # --- opleidingen ---
    def study_id(self, name):
        s = self.study_by_name.get(name)
        if s:
            return s['id']
        level = 'Bachelor' if name.startswith('B ') else ('Associate degree' if name.startswith('Ad ') else 'Overig')
        label = re.sub(r'^(B|Ad) ', '', name)
        sid, n = slug(name), 2
        while any(x['id'] == sid for x in self.studies):
            sid, n = f'{slug(name)}-{n}', n + 1
        s = {'id': sid, 'name': name, 'label': label, 'level': level}
        self.studies.append(s)
        self.study_by_name[name] = s
        return sid

    # --- minors ---
    def find_minor(self, name, inst=None, code=None, allow_loose=False):
        if code:
            for m in self.minors:
                if code in m.get('osiris_codes', []):
                    return m
        n = norm(name)
        if n in self.aliases and self.aliases[n] in self.minor_by_id:
            return self.minor_by_id[self.aliases[n]]
        cands = [m for m in self.minors if n == norm(m['name']) or n in [norm(a) for a in m.get('aliases', [])]]
        if inst:
            cands = [m for m in cands if m.get('institute') in (inst, '', None)]
        if cands:
            return cands[0]
        if not allow_loose:
            return None
        l = loose(name)
        cands = [m for m in self.minors if l == loose(m['name'])]
        if inst:
            cands = [m for m in cands if m.get('institute') in (inst, '', None)]
        return cands[0] if len(cands) == 1 else None

    def new_minor(self, name, inst, kind='minor'):
        mid, n = slug(name) or 'minor', 2
        while mid in self.minor_by_id:
            mid, n = f'{slug(name)}-{n}', n + 1
        m = {'id': mid, 'name': name, 'aliases': [], 'kind': kind, 'institute': inst, 'osiris_codes': [], 'by_year': {}}
        self.minors.append(m)
        self.minor_by_id[mid] = m
        return m

    def offering(self, minor_id, year, term):
        oid = f'{minor_id}@{year}@{term}'
        o = self.off_by_id.get(oid)
        if not o:
            o = {'id': oid, 'minor': minor_id, 'year': year, 'term': term, 'ec': None, 'languages': [], 'enrollment': None,
                 'target': [], 'admitted': None, 'warning': '', 'unconfirmed': False, 'sources': [], 'snapshot': None, 'active': True}
            self.offerings.append(o)
            self.off_by_id[oid] = o
        return o

    def ensure_year(self, year):
        if year not in self.calendar:
            self.calendar[year] = {'label': year, 'terms': {'N': {'label': 'Semester 1 (najaar)', 'start': None, 'end': None},
                                                              'V': {'label': 'Semester 2 (voorjaar)', 'start': None, 'end': None}}, 'events': []}
            print(f'  LET OP: jaar {year} toegevoegd aan calendar.json; vul start- en einddatum van de semesters in.')

    def write(self):
        self.studies.sort(key=lambda s: (s['level'], s['label']))
        self.minors.sort(key=lambda m: m['name'].lower())
        self.offerings.sort(key=lambda o: (o['year'], o['term'], o['minor']))
        save('studies.json', self.studies)
        save('minors.json', self.minors)
        save('offerings.json', self.offerings)
        save('institutes.json', self.institutes)
        save('calendar.json', self.calendar)
        save('sources.json', self.sources)


def add_snapshot(st, source, year, retrieved, file):
    st.sources['snapshots'] = [s for s in st.sources['snapshots'] if not (s['source'] == source and s.get('year') == year and s['retrieved'] == retrieved)]
    st.sources['snapshots'].append({'source': source, 'year': year, 'retrieved': retrieved, 'file': file})


# ---------- osiris ----------
def import_osiris(path):
    exp = json.loads(Path(path).read_text(encoding='utf-8'))
    assert exp.get('kind') == 'osiris-minors', 'Geen Osiris-export'
    st = Store()
    retrieved = exp['retrieved']
    groups = {}
    for it in exp['items']:
        inst = st.inst_code(it['institute'])
        groups.setdefault((norm(it['name']), inst), []).append((it, inst))
    seen, years = set(), set()
    created = 0
    for (_, inst), rows in groups.items():
        first = rows[0][0]
        m = st.find_minor(first['name'], inst, first['code'])
        if not m:
            m = st.new_minor(re.sub(r'\s+', ' ', first['name']).strip(), inst)
            created += 1
        m.setdefault('osiris_codes', [])
        for it, _ in rows:
            if it['code'] not in m['osiris_codes']:
                m['osiris_codes'].append(it['code'])
        starts = {(s['year'], TERM.get(s['block'], s['block'])) for it, _ in rows for s in it['starts']}
        windows = sorted({(w['from'], w['to']) for it, _ in rows for w in it['enrollment']})
        langs = []
        for it, _ in rows:
            for l in it['languages']:
                c = LANG.get(l.lower(), l[:2].upper())
                if c not in langs:
                    langs.append(c)
        target = sorted({st.study_id(n) for it, _ in rows for n in it['target']})
        admitted = sorted({st.study_id(n) for it, _ in rows for n in it['admitted']})
        for year, term in sorted(starts):
            years.add(year)
            st.ensure_year(year)
            o = st.offering(m['id'], year, term)
            o.update({'ec': first['ec'], 'languages': langs, 'target': target,
                      'admitted': admitted if (admitted or target) else None, 'snapshot': retrieved, 'active': True})
            if 'osiris' not in o['sources']:
                o['sources'].append('osiris')
            seen.add(o['id'])
        # inschrijfperiode hoort bij het voorjaar als dat bestaat, anders bij het eerste startmoment
        if windows:
            by_year = {}
            for year, term in sorted(starts):
                by_year.setdefault(year, []).append(term)
            for year, terms in by_year.items():
                t = 'V' if 'V' in terms else terms[0]
                w = windows[0]
                st.offering(m['id'], year, t)['enrollment'] = {'from': amsterdam_date(w[0]), 'to': amsterdam_date(w[1])}
    removed = 0
    for o in st.offerings:
        if o['year'] in years and 'osiris' in o['sources'] and o['id'] not in seen and o['active']:
            o['active'] = False
            removed += 1
    for y in years:
        add_snapshot(st, 'osiris', y, retrieved, Path(path).name)
    st.write()
    print(f'Osiris: {len(exp["items"])} regels -> {len(groups)} minors ({created} nieuw), {len(seen)} aanbiedingen, {removed} gedeactiveerd, jaren: {sorted(years)}')


# ---------- hint ----------
STOP = r'(?:Periode|Literatuur|Toelatingseisen|Achtergrondinformatie|Minor Choice Week|Minor keuzeweek|Minorbeurs|Minor fair|Minorcode:)'


def section(text, label, stops=STOP, cap=4000):
    m = re.search(rf'(?:^|\n){label}\n(.*?)(?=\n{stops}|\Z)', text, re.S)
    return (m.group(1).strip()[:cap]) if m else ''


def parse_hint(text):
    lines = [l for l in text.split('\n') if l.strip()]
    out = {}
    m = re.search(r'Locatie[ \n]*([^\n]+)', text)
    out['location'] = m.group(1).strip() if m else ''
    m = re.search(r'Studiepunten[ \n]*(\d+)[ \n]*(EC[^\n]*)', text)
    out['ec_text'] = f'{m.group(1)} {m.group(2).strip()}' if m else ''
    out['ec'] = int(m.group(1)) if m else None
    m = re.search(r'Instituut\n([^\n]+)', text)
    out['institute_text'] = m.group(1).strip() if m else ''
    m = re.search(r'Voertaal[ \n]*([^\n]+)', text)
    out['language_text'] = m.group(1).strip() if m else ''
    out['tagline'] = lines[1].strip()[:400] if len(lines) > 1 and len(lines[1]) > 25 and not re.match(r'(Co.rdinator|Locatie|Online)', lines[1]) else ''
    m = re.search(r'Periode\n([^\n]+)', text)
    out['period'] = m.group(1).strip() if m else ''
    desc = section(text, 'Omschrijving')
    if not desc:
        m = re.search(r'Studiepunten[ \n]*\d+[ \n]*EC[^\n]*\n(?:Voertaal[ \n]*[^\n]+\n)?(?:Thema[ \n]*[^\n]+\n)?(.*?)(?=\nToelatingseisen|\nAchtergrondinformatie|\nLet op!|\Z)', text, re.S)
        desc = m.group(1).strip()[:4000] if m else ''
    out['description'] = desc
    out['admission'] = section(text, 'Toelatingseisen', r'(?:Achtergrondinformatie|Minor Choice Week|Minor keuzeweek|Minorcode:)')
    out['background'] = section(text, 'Achtergrondinformatie', r'(?:Minor Choice Week|Minor keuzeweek|Minorbeurs|Minor fair|Minorcode:)', 5000)
    m = re.search(r'Minorcode:\s*(\S+)', text)
    out['code'] = m.group(1) if m else ''
    m = re.search(r'Met wie werk je samen\?[^\n]*\n([^\n]+)', text)
    out['participants_text'] = m.group(1).strip() if m else ''
    return out


def import_hint(path, year):
    exp = json.loads(Path(path).read_text(encoding='utf-8'))
    assert exp.get('kind') == 'hint-minors', 'Geen HINT-export'
    st = Store()
    st.ensure_year(year)
    retrieved = exp['retrieved']
    FORM = {'Voltijd': 'VT', 'Deeltijd': 'DT', 'Duaal': 'DU'}
    created, matched, skipped = [], 0, []
    for it in exp['items']:
        if it.get('error') or not it.get('name'):
            skipped.append(it.get('listName') or it['url'])
            continue
        p = parse_hint(it['text'])
        url = it['url']
        is_prog = '/customize/' in url
        inst = ''
        pm = re.search(r'/Instituten/([A-Z]+)/', url)
        if pm:
            inst = pm.group(1)
        elif p['institute_text']:
            inst = st.inst_code(p['institute_text'].split(' - ', 1)[-1])
        name = it['name'].strip()
        m = st.find_minor(name, inst or None, allow_loose=True) or (st.find_minor(it['listName'], allow_loose=True) if it.get('listName') else None)
        if not m:
            m = st.new_minor(name, inst, 'programma' if is_prog else 'minor')
            created.append(name)
        else:
            matched += 1
        entry = {'url': url, 'link': it['link'] if it['link'].startswith('/') else '', 'forms': [FORM[t] for t in it.get('tabs', []) if t in FORM],
                 'location': p['location'], 'ec_text': p['ec_text'], 'tagline': p['tagline'], 'period': p['period'], 'code': p['code'],
                 'description': p['description'], 'admission': p['admission'], 'background': p['background'],
                 'participants_text': p['participants_text'], 'language_text': p['language_text'], 'retrieved': retrieved}
        m.setdefault('by_year', {})[year] = entry
        if not m.get('institute') and inst:
            m['institute'] = inst
        # minors die alleen op HINT staan krijgen een aanbieding op basis van de periode
        if not is_prog and not any(o['minor'] == m['id'] and o['year'] == year for o in st.offerings):
            pr = re.search(r'(\d{1,2})-(\d{1,2})-(\d{4})', p['period'])
            if pr:
                month = int(pr.group(2))
                term = 'N' if month >= 8 else 'V'
                o = st.offering(m['id'], year, term)
                o.update({'ec': p['ec'], 'languages': [], 'admitted': None, 'target': [], 'snapshot': retrieved})
                if 'hint' not in o['sources']:
                    o['sources'].append('hint')
    add_snapshot(st, 'hint', year, retrieved, Path(path).name)
    st.write()
    print(f'HINT: {len(exp["items"])} pagina\'s, {matched} bestaande minors bijgewerkt, {len(created)} nieuw: {created}')
    if skipped:
        print('  overgeslagen:', skipped)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    a = sub.add_parser('osiris'); a.add_argument('file')
    b = sub.add_parser('hint'); b.add_argument('file'); b.add_argument('--year', required=True, help='collegejaar van het HINT-overzicht, bijv. 2026-2027')
    args = ap.parse_args()
    if args.cmd == 'osiris':
        import_osiris(args.file)
    else:
        import_hint(args.file, args.year)


if __name__ == '__main__':
    sys.exit(main())
