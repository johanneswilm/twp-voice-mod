"""Build per-actor voice assignment (cache/voice_assign.json).

Gender: f0-measured from the actors' English lines (cache/actor_f0b.json),
with corrections for characters whose performance pitch misleads
(Ransome's shrill clown voice, squeaky Pigeon Brothers, dog, etc.).

Voices: gender-appropriate pools from cache/voice_f0.json (German MLS
multi-speaker model gives ~40 distinct speakers). Curated leads get explicit
combos; the rest are filled deterministically with collision avoidance so
every actor sounds distinct per language.
"""
import hashlib
import json

actor_f0 = json.load(open('cache/actor_f0b.json'))

OVERRIDES = {
    'RANSOME': 'm', 'PIGEON1': 'm', 'PIGEON2': 'm', 'STARSHIPMAN': 'm',
    'DOUG': 'm', 'HOTELKID': 'f', 'MALEGHOST1': 'm', 'FEMALEGHOST1': 'f',
}
GENDER = {a: OVERRIDES.get(a, v['gender'] if v['gender'] != '?' else 'm')
          for a, v in actor_f0.items()}

DE_MLS_M = [0, 1, 3, 6, 7, 8, 9, 11, 13, 16, 18, 20, 21, 22, 23, 24, 25, 27, 29, 32, 34, 39]
DE_MLS_F = [2, 4, 5, 10, 12, 14, 15, 17, 19, 26, 28, 30, 31, 33, 35, 36, 37, 38]

POOL = {
    ('de', 'm'): [{'voice': 'de_DE-thorsten-high', 'speaker': None},
                  {'voice': 'de_DE-thorsten-medium', 'speaker': None},
                  {'voice': 'de_DE-pavoque-low', 'speaker': None},
                  {'voice': 'de_DE-karlsson-low', 'speaker': None}] +
                 [{'voice': 'de_DE-mls-medium', 'speaker': s} for s in DE_MLS_M],
    ('de', 'f'): [{'voice': 'de_DE-kerstin-low', 'speaker': None},
                  {'voice': 'de_DE-ramona-low', 'speaker': None}] +
                 [{'voice': 'de_DE-mls-medium', 'speaker': s} for s in DE_MLS_F],
    ('es', 'm'): [{'voice': 'es_ES-davefx-medium', 'speaker': None},
                  {'voice': 'es_MX-ald-medium', 'speaker': None},
                  {'voice': 'es_ES-sharvard-medium', 'speaker': 0}],
    ('es', 'f'): [{'voice': 'es_AR-daniela-high', 'speaker': None},
                  {'voice': 'es_ES-sharvard-medium', 'speaker': 1},
                  {'voice': 'es_MX-claude-high', 'speaker': None},
                  {'voice': 'es_ES-mls_10246-low', 'speaker': None},
                  {'voice': 'es_ES-mls_9972-low', 'speaker': None}],
}

LADDER = {('de', 'm'): [1.00, 0.96, 1.04, 1.09, 1.14, 0.91], ('de', 'f'): [1.00, 0.96, 1.04, 0.91, 1.09],
          ('es', 'm'): [1.00, 0.94, 1.06, 0.88, 1.12, 0.97, 1.03, 0.84, 1.16, 0.91, 1.09, 0.81, 1.19, 0.86, 1.22, 0.78],
          ('es', 'f'): [1.00, 0.94, 1.06, 0.88, 1.12, 0.97, 1.16]}
SPEEDS = [1.00, 0.96, 1.04]

def V(voice, speaker, pitch, speed):
    return {'voice': voice, 'speaker': speaker, 'pitch': pitch, 'speed': speed}

CURATED = {
    'RAY':         {'de': V('de_DE-thorsten-high', None, 1.00, 1.00), 'es': V('es_ES-davefx-medium', None, 1.00, 1.00)},
    'REYES':       {'de': V('de_DE-mls-medium', 1, 1.00, 1.00), 'es': V('es_MX-ald-medium', None, 0.94, 1.00)},
    'DELORES':     {'de': V('de_DE-mls-medium', 14, 1.00, 1.00), 'es': V('es_AR-daniela-high', None, 1.00, 1.00)},
    'RANSOME':     {'de': V('de_DE-thorsten-medium', None, 1.18, 0.95), 'es': V('es_ES-davefx-medium', None, 1.20, 0.95)},
    'FRANKLIN':    {'de': V('de_DE-pavoque-low', None, 1.00, 1.00), 'es': V('es_MX-ald-medium', None, 1.00, 1.00)},
    'CHUCK':       {'de': V('de_DE-mls-medium', 3, 1.00, 1.00), 'es': V('es_ES-sharvard-medium', 0, 1.00, 1.00)},
    'HEADGHOST':   {'de': V('de_DE-karlsson-low', None, 1.00, 0.92), 'es': V('es_ES-sharvard-medium', 0, 0.86, 0.92)},
    'HINTTRON':    {'de': V('de_DE-mls-medium', 23, 1.00, 1.06), 'es': V('es_MX-ald-medium', None, 1.02, 1.06)},
    'TRONMACHINE': {'de': V('de_DE-mls-medium', 16, 0.94, 0.90), 'es': V('es_ES-davefx-medium', None, 0.88, 0.90)},
    'COMPUTER':    {'de': V('de_DE-mls-medium', 10, 1.06, 1.00), 'es': V('es_MX-claude-high', None, 1.02, 1.00)},
    'HOTELKID':    {'de': V('de_DE-mls-medium', 12, 1.06, 0.95), 'es': V('es_AR-daniela-high', None, 1.15, 0.95)},
}


def h(s):
    return int(hashlib.md5(s.encode()).hexdigest(), 16)


voice_f0 = json.load(open('cache/voice_f0.json'))


def build():
    assign = {}
    used = {lang: set() for lang in ('de', 'es')}
    for lang in ('de', 'es'):
        for a, e in CURATED.items():
            c = e[lang]
            used[lang].add((c['voice'], c['speaker'], c['pitch']))
    for a in sorted(GENDER):
        g = GENDER[a]
        entry = {'gender': g}
        for lang in ('de', 'es'):
            key = (lang, g)
            if a in CURATED:
                entry[lang] = dict(CURATED[a][lang])
                continue
            pool = POOL[key]
            ladder = LADDER[key]
            # deterministic candidate order: bases starting from a hash offset
            order = pool[h(a + lang) % len(pool):] + pool[:h(a + lang) % len(pool)]
            chosen = None
            for base in order:
                vf = voice_f0.get(base['voice'] + (f"|{base['speaker']}" if base['speaker'] is not None else ''))
                f0 = vf[0] if vf else (130 if g == 'm' else 200)
                # pitch candidates that land the effective f0 in a natural range
                if g == 'm':
                    lo, hi = 95.0, 155.0
                else:
                    lo, hi = 176.0, 255.0
                cands = []
                for p in ladder:
                    eff = f0 * p
                    if lo <= eff <= hi:
                        cands.append(p)
                if not cands:
                    cands = ladder
                for p in cands:
                    k = (base['voice'], base['speaker'], p)
                    if k not in used[lang]:
                        chosen = (base, p)
                        used[lang].add(k)
                        break
                if chosen:
                    break
            assert chosen, f'pool exhausted for {a} {lang}'
            base, p = chosen
            entry[lang] = V(base['voice'], base['speaker'], p, SPEEDS[h(a + 's') % len(SPEEDS)])
        assign[a] = entry
    json.dump(assign, open('cache/voice_assign.json', 'w'), indent=1)
    print(f'assigned {len(assign)} actors')
    # report curated + sample
    for a in ('RAY', 'REYES', 'DELORES', 'RANSOME'):
        e = assign[a]
        print(a, e['de'], e['es'])


if __name__ == '__main__':
    build()
