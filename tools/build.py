#!/usr/bin/env python3
"""Bouwt de interactieve rapportpagina (en optioneel een SQLite-database) uit de JSON-dataset.

Gebruik:
    python tools/build.py                 # schrijft dist/minor-advies-hr.html
    python tools/build.py --sqlite        # schrijft daarnaast dist/minors.db
    python tools/build.py --out pad.html
"""
import argparse
import datetime as dt
import json
import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get('MINOR_TOOL_DATA') or ROOT / 'data')
LANG_ORDER = ['NL', 'EN']


def load(name, default=None):
    p = DATA / name
    return json.loads(p.read_text(encoding='utf-8')) if p.exists() else default


def cap(t, n):
    t = (t or '').strip()
    return t if len(t) <= n else t[:n].rsplit(' ', 1)[0] + '\u2026'


def build_payload():
    studies = load('studies.json', [])
    minors = load('minors.json', [])
    offs = load('offerings.json', [])
    inst = load('institutes.json', [])
    cal = load('calendar.json', {})
    ass = load('assessments.json', {'profiles': []})
    srcs = load('sources.json', {'sources': [], 'snapshots': []})

    used = set()
    for o in offs:
        used.update(o.get('target') or [])
        used.update(o.get('admitted') or [])
    for p in ass['profiles']:
        used.update(p['studies'])
    studies = [s for s in studies if s['id'] in used]
    sidx = {s['id']: i for i, s in enumerate(studies)}

    act_minor_ids = {o['minor'] for o in offs}
    minors = [m for m in minors if m['id'] in act_minor_ids]
    midx = {m['id']: i for i, m in enumerate(minors)}

    det = {}
    for i, m in enumerate(minors):
        for y, e in (m.get('by_year') or {}).items():
            det.setdefault(str(i), {})[y] = {
                'tag': cap(e.get('tagline'), 300), 'desc': cap(e.get('description'), 1100), 'adm': cap(e.get('admission'), 900),
                'bg': cap(e.get('background'), 1100), 'per': e.get('period', ''), 'code': e.get('code', ''), 'loc': e.get('location', ''),
                'ecx': e.get('ec_text', ''), 'forms': e.get('forms', []), 'url': e.get('url', ''), 'link': e.get('link', ''),
            }

    def lang(l):
        ls = sorted(l or [], key=lambda x: LANG_ORDER.index(x) if x in LANG_ORDER else 9)
        return '/'.join(ls)

    off = []
    for o in offs:
        off.append({
            'm': midx[o['minor']], 'y': o['year'], 't': o['term'], 'ec': o.get('ec'), 'l': lang(o.get('languages')),
            'e': [o['enrollment']['from'], o['enrollment']['to']] if o.get('enrollment') else None,
            'o': sorted(sidx[s] for s in (o.get('target') or []) if s in sidx),
            'a': None if o.get('admitted') is None else sorted(sidx[s] for s in o['admitted'] if s in sidx),
            'w': o.get('warning', ''), 'u': 1 if o.get('unconfirmed') else 0, 'n': o.get('enroll_note', ''),
            'src': o.get('sources', []), 'act': 1 if o.get('active', True) else 0,
        })

    prof = []
    for p in ass['profiles']:
        prof.append({
            'id': p['id'], 'l': p['label'], 'st': [sidx[s] for s in p['studies'] if s in sidx], 'basis': p.get('basis_year', ''),
            'desc': p.get('description', ''), 'crit': [{'k': c['key'], 'l': c['label'], 'd': c['description'], 'w': c['weight']} for c in p['criteria']],
            'items': {str(midx[k]): {'t': v['type'], 's': v['scores'], 'n': v.get('note', ''), 'star': 1 if v.get('star') else 0}
                      for k, v in p['items'].items() if k in midx},
            'comm': [{'m': [midx[x] for x in c['minors'] if x in midx], 's': c['summary'], 'a': c['admission']} for c in p.get('commentary', [])],
        })

    return {
        'built': dt.date.today().isoformat(),
        'studies': [{'id': s['id'], 'l': s['label'], 'lv': s['level']} for s in studies],
        'inst': {i['code']: i['name'] for i in inst},
        'cal': {y: {'terms': {t: {'l': v['label'], 's': v.get('start'), 'e': v.get('end')} for t, v in c['terms'].items()},
                    'events': [{'t': e.get('term'), 'd': e['date'], 'l': e['label']} for e in c.get('events', [])]} for y, c in cal.items()},
        'minors': [{'id': m['id'], 'n': m['name'], 'k': 'p' if m.get('kind') == 'programma' else 'm', 'i': m.get('institute', '')} for m in minors],
        'det': det, 'off': off, 'prof': prof, 'sources': srcs,
    }


def write_html(payload, out):
    tpl = (ROOT / 'tools' / 'template.html').read_text(encoding='utf-8')
    blob = json.dumps(payload, ensure_ascii=False, separators=(',', ':')).replace('</', '<\\/')
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(tpl.replace('__DATA__', blob), encoding='utf-8')
    print(f'HTML: {out} ({out.stat().st_size // 1024} KB)')


def write_sqlite(out):
    studies, minors, offs = load('studies.json', []), load('minors.json', []), load('offerings.json', [])
    inst, cal = load('institutes.json', []), load('calendar.json', {})
    ass = load('assessments.json', {'profiles': []})
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        out.unlink()
    db = sqlite3.connect(out)
    db.executescript('''
    CREATE TABLE institutes(code TEXT PRIMARY KEY, name TEXT);
    CREATE TABLE studies(id TEXT PRIMARY KEY, name TEXT, label TEXT, level TEXT);
    CREATE TABLE minors(id TEXT PRIMARY KEY, name TEXT, kind TEXT, institute TEXT, osiris_codes TEXT);
    CREATE TABLE minor_content(minor_id TEXT, year TEXT, url TEXT, location TEXT, ec_text TEXT, tagline TEXT, period TEXT, code TEXT,
        description TEXT, admission TEXT, background TEXT, forms TEXT, PRIMARY KEY(minor_id, year));
    CREATE TABLE terms(year TEXT, term TEXT, label TEXT, start_date TEXT, end_date TEXT, PRIMARY KEY(year, term));
    CREATE TABLE offerings(id TEXT PRIMARY KEY, minor_id TEXT, year TEXT, term TEXT, ec INTEGER, languages TEXT,
        enroll_from TEXT, enroll_to TEXT, warning TEXT, unconfirmed INTEGER, sources TEXT, snapshot TEXT, active INTEGER, admission_known INTEGER);
    CREATE TABLE offering_target(offering_id TEXT, study_id TEXT);
    CREATE TABLE offering_admitted(offering_id TEXT, study_id TEXT);
    CREATE TABLE assessments(profile TEXT, minor_id TEXT, type TEXT, c INTEGER, t INTEGER, d INTEGER, a INTEGER, p INTEGER, w INTEGER, l INTEGER,
        total REAL, note TEXT, PRIMARY KEY(profile, minor_id));
    CREATE VIEW offering_overview AS
        SELECT o.id, o.year, o.term, m.name AS minor, m.institute, o.ec, o.languages, o.enroll_from, o.enroll_to, o.active
        FROM offerings o JOIN minors m ON m.id = o.minor_id;
    ''')
    db.executemany('INSERT INTO institutes VALUES(?,?)', [(i['code'], i['name']) for i in inst])
    db.executemany('INSERT INTO studies VALUES(?,?,?,?)', [(s['id'], s['name'], s['label'], s['level']) for s in studies])
    db.executemany('INSERT INTO minors VALUES(?,?,?,?,?)', [(m['id'], m['name'], m.get('kind'), m.get('institute'), ','.join(m.get('osiris_codes', []))) for m in minors])
    for m in minors:
        for y, e in (m.get('by_year') or {}).items():
            db.execute('INSERT INTO minor_content VALUES(?,?,?,?,?,?,?,?,?,?,?,?)', (m['id'], y, e.get('url'), e.get('location'), e.get('ec_text'), e.get('tagline'),
                       e.get('period'), e.get('code'), e.get('description'), e.get('admission'), e.get('background'), ','.join(e.get('forms', []))))
    for y, c in cal.items():
        for t, v in c['terms'].items():
            db.execute('INSERT INTO terms VALUES(?,?,?,?,?)', (y, t, v['label'], v.get('start'), v.get('end')))
    for o in offs:
        w = o.get('enrollment') or {}
        db.execute('INSERT INTO offerings VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)', (o['id'], o['minor'], o['year'], o['term'], o.get('ec'), ','.join(o.get('languages', [])),
                   w.get('from'), w.get('to'), o.get('warning', ''), 1 if o.get('unconfirmed') else 0, ','.join(o.get('sources', [])), o.get('snapshot'),
                   1 if o.get('active', True) else 0, 0 if o.get('admitted') is None else 1))
        db.executemany('INSERT INTO offering_target VALUES(?,?)', [(o['id'], s) for s in o.get('target') or []])
        db.executemany('INSERT INTO offering_admitted VALUES(?,?)', [(o['id'], s) for s in o.get('admitted') or []])
    wt = [1, 1, 1, 1, 1, 1, 1]
    for p in ass['profiles']:
        ws = [c['weight'] for c in p['criteria']]
        for k, v in p['items'].items():
            s = v['scores']
            tot = round(sum(a * b for a, b in zip(s, ws)) / 100 + 1e-9, 1)
            db.execute('INSERT INTO assessments VALUES(?,?,?,?,?,?,?,?,?,?,?,?)', (p['id'], k, v['type'], *s, tot, v.get('note', '')))
    db.commit()
    db.close()
    print(f'SQLite: {out}')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--out', default=str(ROOT / 'dist' / 'minor-advies-hr.html'))
    ap.add_argument('--sqlite', action='store_true')
    a = ap.parse_args()
    payload = build_payload()
    write_html(payload, Path(a.out))
    if a.sqlite:
        write_sqlite(ROOT / 'dist' / 'minors.db')


if __name__ == '__main__':
    sys.exit(main())
