#!/usr/bin/env python3
"""Controleert de dataset op referentiële integriteit. Gebruik: python tools/validate.py"""
import json
import os
import sys
from pathlib import Path

DATA = Path(os.environ.get('MINOR_TOOL_DATA') or Path(__file__).resolve().parent.parent / 'data')


def load(n, d=None):
    p = DATA / n
    return json.loads(p.read_text(encoding='utf-8')) if p.exists() else d


def main():
    studies = load('studies.json', [])
    minors = load('minors.json', [])
    offs = load('offerings.json', [])
    inst = load('institutes.json', [])
    cal = load('calendar.json', {})
    ass = load('assessments.json', {'profiles': []})
    errs, warns = [], []
    sid = {s['id'] for s in studies}
    mid = {m['id'] for m in minors}
    codes = {i['code'] for i in inst}
    if len(sid) != len(studies):
        errs.append('dubbele study-id\'s')
    if len(mid) != len(minors):
        errs.append('dubbele minor-id\'s')
    if len({o['id'] for o in offs}) != len(offs):
        errs.append('dubbele offering-id\'s')
    for m in minors:
        if m.get('institute') and m['institute'] not in codes:
            errs.append(f'minor {m["id"]}: onbekend instituut {m["institute"]}')
        if m.get('kind') not in ('minor', 'programma'):
            errs.append(f'minor {m["id"]}: ongeldige kind {m.get("kind")}')
    for o in offs:
        if o['minor'] not in mid:
            errs.append(f'offering {o["id"]}: onbekende minor')
        y = cal.get(o['year'])
        if not y:
            errs.append(f'offering {o["id"]}: jaar ontbreekt in calendar.json')
        elif o['term'] not in y['terms']:
            errs.append(f'offering {o["id"]}: term {o["term"]} ontbreekt in calendar.json')
        for k in ('target', 'admitted'):
            for s in (o.get(k) or []):
                if s not in sid:
                    errs.append(f'offering {o["id"]}: onbekende opleiding {s} in {k}')
        w = o.get('enrollment')
        if w and not (w['from'] <= w['to']):
            errs.append(f'offering {o["id"]}: inschrijfperiode omgekeerd')
    for y, c in cal.items():
        for t, v in c['terms'].items():
            if not v.get('start') or not v.get('end'):
                warns.append(f'calendar {y}/{t}: start- of einddatum ontbreekt')
    for p in ass['profiles']:
        n = len(p['criteria'])
        if sum(c['weight'] for c in p['criteria']) != 100:
            warns.append(f'profiel {p["id"]}: gewichten tellen niet op tot 100')
        for s in p['studies']:
            if s not in sid:
                errs.append(f'profiel {p["id"]}: onbekende opleiding {s}')
        for k, it in p['items'].items():
            if k not in mid:
                errs.append(f'profiel {p["id"]}: onbekende minor {k}')
            if len(it['scores']) != n or not all(1 <= x <= 10 for x in it['scores']):
                errs.append(f'profiel {p["id"]}/{k}: ongeldige scores')
            if it['type'] not in ('verdiepend', 'verbredend'):
                errs.append(f'profiel {p["id"]}/{k}: ongeldig type')
    years = sorted({o['year'] for o in offs})
    print(f'{len(studies)} opleidingen, {len(minors)} minors, {len(offs)} aanbiedingen, jaren: {years}')
    for w in warns:
        print('WAARSCHUWING:', w)
    for e in errs:
        print('FOUT:', e)
    print('OK' if not errs else f'{len(errs)} fout(en)')
    return 1 if errs else 0


if __name__ == '__main__':
    sys.exit(main())
