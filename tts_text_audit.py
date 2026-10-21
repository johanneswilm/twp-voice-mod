"""Compare the text as PRINTED in the game with the text as SPOKEN by the
synthetic voices - and export both as a spreadsheet for LibreOffice Calc.

Background
----------
The game's localisation files (ThimbleweedText_{de,es}.tsv) are *not* the
strings the game shows.  The engine (`Text::loadLanguageTable` in
libThimbleweedPark.so) removes every backslash escape while loading the TSV
(so `\"` is printed as `"`), and `Obtor::parseSayLine` strips a leading
"(...)" delivery direction and a leading "{...}" engine command before the
line is shown.

The TTS pipeline used to feed the *raw* TSV string to piper, so the voices
read things the player never sees:

  * the backslash of `\"`   -> "Wechsel" / "backslash" (German voices)
  * the leading "(...)"     -> "sarcastic", "dont_translate", "fast", ...
  * censored words          -> "ver*Biep*te" became "ver te"
  * the "#F"/"#M" suffix    -> "Nummer Eff" / "hash Emene"
  * "%d" printf placeholders-> "Prozent de"

This script rebuilds both strings for every text id and writes a spreadsheet:

  text_audit_de_es.xlsx  (main deliverable, opens in LibreOffice Calc)
  text_audit_de_es.csv   (same rows, CSV for grep/CI)
  text_audit_flags.csv   (only the rows with issues)

Usage:  python3 tts_text_audit.py
"""
import csv
import json
import os
import re
import sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)

from tts_text import (BEEP_RE, LEAD_PAREN, PRINTF_PLACEHOLDER_RE,  # noqa: E402
                       VOICE_MARKER_RE, clean_text, clean_text_legacy, game_text,
                       game_unescape)
from tts_censored import replace_censored  # noqa: E402

PACK_OBB = 'main.65.com.terribletoybox.thimbleweedparkandroid.obb'
LANGS = ('en', 'de', 'es')
TTS_LANGS = ('de', 'es')
SNAPSHOT = 'cache/spoken_text_before_fix.json'

# --- what piper does with the leftovers ------------------------------------
# measured with faster-whisper on freshly synthesised samples
# (probe: "Die Zahl ist eins <CHAR> zwei." / "El numero es uno <CHAR> dos.").
# Only characters that are actually spoken out loud are listed.
PIPER_SAYS = {
    'de': {
        '\\': 'Wechsel / backslash',
        '#': 'Nummer',
        '$': 'Dollar',
        '%': 'Prozent',
        '~': 'Tilde',
        '=': 'gleich',
        '@': 'at',
        '+': 'plus',
        '&': 'und',
    },
    'es': {
        '\\': '(nothing)',
        '#': 'hash / almadía',
        '$': 'dólar',
        '%': 'por ciento',
        '~': 'tilde',
        '=': 'igual',
        '@': 'arroba',
        '+': 'más',
        '&': 'y',
        '/': 'barra',
        '*': 'asterisco',
    },
}


def read_tsv(lang):
    rows = list(csv.reader(open(f'ThimbleweedText_{lang}.tsv', encoding='utf-8').read().splitlines(),
                             delimiter='\t'))
    return {r[0]: r[1] for r in rows[1:] if len(r) >= 2}


def read_actors():
    """text id -> list of actors that own a voice clip for that line.

    A line that has an <ACTOR>_<id>.ogg in the pack is spoken in the game
    (a "talkie"); everything else is UI text that is only printed.
    """
    actors = defaultdict(list)
    try:
        from ggpack3 import GGPack
        pack = GGPack(PACK_OBB)
    except Exception as e:                                   # pragma: no cover
        print(f'! cannot open pack ({e}) - no actor/clip info', file=sys.stderr)
        return actors
    for name in pack.entries:
        m = re.match(r'^([A-Z0-9]+)_(\d{5})\.ogg$', name)
        if m:
            actors[m.group(2)].append(m.group(1))
    return actors


def existing_tts_clips(lang):
    """text ids that already have a generated clip in tts_out/<lang>."""
    out = set()
    d = f'tts_out/{lang}'
    if not os.path.isdir(d):
        return out
    for f in os.listdir(d):
        m = re.match(r'^([a-z0-9]+)_(\d{5})_%s\.ogg$' % lang, f)
        if m:
            out.add(m.group(2))
    return out


# symbols that piper says out loud although the English line reads them out
# the same way -> not a bug
EQUIVALENT = {'$', '%', '&', '+'}


def classify(lang, raw, spoken):
    """Return (issue tags, detail, state) for one line.

    "state" says what happened to the issue:
      fixed       - the new pipeline no longer feeds the offending characters
      equivalent  - piper says the symbol, but the English line says it too
      check       - piper says something the player does not hear in English
      open        - still audible, needs a manual decision
    """
    issues = []
    detail = []
    state = []
    g = game_unescape(raw)

    if '\\' in raw:
        issues.append('backslash')
        detail.append(f'{raw.count(chr(92))} backslash(es) - piper says '
                      f'"{PIPER_SAYS[lang]["\\"]}"')
        state.append('fixed' if '\\' not in spoken else 'open')

    m = LEAD_PAREN.match(g)
    if m:
        issues.append('direction')
        only_dir = not g[m.end():].strip()
        detail.append(f'leading direction "{m.group(0).strip()}" is read out loud'
                      + (' (the line is nothing but that direction)' if only_dir else ''))
        if m.group(0).strip().strip('()') in spoken:
            state.append('check' if only_dir else 'open')
        else:
            state.append('fixed')

    if VOICE_MARKER_RE.search(raw):
        issues.append('voice-marker')
        detail.append(f'"{VOICE_MARKER_RE.search(raw).group(0).strip()}" - a translation '
                      f'marker, not text - piper says "{PIPER_SAYS[lang].get("#", "hash")}"')
        state.append('fixed' if '#' not in spoken else 'open')

    if PRINTF_PLACEHOLDER_RE.search(raw):
        issues.append('printf')
        detail.append(f'printf placeholder "{PRINTF_PLACEHOLDER_RE.search(raw).group(0)}" '
                      f'(the game substitutes a value)')
        state.append('open' if '%' in spoken else 'fixed')

    masks = list(re.finditer(r'\*([^*]*)\*', raw))
    if any(BEEP_RE.search(m.group(1)) for m in masks):
        issues.append('censored-word')
        beep = [m.group(1) for m in masks if BEEP_RE.search(m.group(1))]
        still_beeps = all(b.lower() in spoken.lower() for b in beep)
        if still_beeps:
            detail.append('the censored beep word is dropped or split by the voice')
            state.append('open')
        else:
            detail.append('the censored word is spoken as a milder word '
                          '(see the "censored words" sheet)')
            state.append('fixed')

    if len(masks) * 2 != raw.count('*'):
        issues.append('unbalanced-mask')
        detail.append('unmatched "*" in the source text')
        state.append('open')

    for ch in sorted(set(spoken) & set(PIPER_SAYS[lang])):
        if ch == '\\':
            continue                       # already reported as "backslash"
        issues.append(f'symbol:{ch}')
        detail.append(f'"{ch}" - piper says "{PIPER_SAYS[lang][ch]}"')
        if ch in EQUIVALENT:
            state.append('equivalent')
        else:
            state.append('check')
    return issues, detail, state


# --- output ----------------------------------------------------------------
HEAD = [
    ('text_id', 'text_id'),
    ('actors', 'actor(s)'),
    ('talkie', 'spoken in game'),
    ('clip_de', 'de clip'),
    ('clip_es', 'es clip'),
    ('en_game', 'EN printed in game'),
    ('de_game', 'DE printed in game'),
    ('de_spoken', 'DE spoken by the voice (now)'),
    ('de_before', 'DE spoken (before the fix)'),
    ('de_issues', 'DE issues'),
    ('de_state', 'DE state'),
    ('de_detail', 'DE issue detail'),
    ('es_game', 'ES printed in game'),
    ('es_spoken', 'ES spoken by the voice (now)'),
    ('es_before', 'ES spoken (before the fix)'),
    ('es_issues', 'ES issues'),
    ('es_state', 'ES state'),
    ('es_detail', 'ES issue detail'),
]


def load_snapshot(texts):
    """Keep the text the voices were fed before the fix (for reference)."""
    snap = {}
    if os.path.exists(SNAPSHOT):
        with open(SNAPSHOT) as fh:
            snap = json.load(fh)
    changed = False
    for lang in TTS_LANGS:
        snap.setdefault(lang, {})
        for tid, raw in texts[lang].items():
            if tid not in snap[lang]:
                snap[lang][tid] = clean_text_legacy(raw)
                changed = True
    if changed:
        os.makedirs('cache', exist_ok=True)
        with open(SNAPSHOT, 'w') as fh:
            json.dump(snap, fh, ensure_ascii=False)
        print(f'wrote snapshot {SNAPSHOT}')
    return snap


def main():
    texts = {lang: read_tsv(lang) for lang in LANGS}
    actors = read_actors()
    clips = {lang: existing_tts_clips(lang) for lang in TTS_LANGS}
    snap = load_snapshot(texts)

    ids = sorted(set(texts['en']) | set(texts['de']) | set(texts['es']))
    rows = []
    stats = {lang: Counter() for lang in TTS_LANGS}
    for tid in ids:
        raw = {lang: texts[lang].get(tid, '') for lang in LANGS}
        row = {
            'text_id': tid,
            'actors': ' '.join(sorted(set(actors.get(tid, [])))),
            'talkie': 'y' if actors.get(tid) else '',
            'clip_de': 'y' if tid in clips['de'] else '',
            'clip_es': 'y' if tid in clips['es'] else '',
        }
        for lang in LANGS:
            row[f'{lang}_game'] = game_text(raw[lang], lang)
        for lang in TTS_LANGS:
            spoken = clean_text(raw[lang], lang)
            row[f'{lang}_spoken'] = spoken
            row[f'{lang}_before'] = snap[lang].get(tid, '')
            issues, detail, state = classify(lang, raw[lang], spoken)
            row[f'{lang}_issues'] = '; '.join(issues)
            row[f'{lang}_state'] = '; '.join(state)
            row[f'{lang}_detail'] = ' | '.join(detail)
            for tag, st in zip(issues, state):
                stats[lang][f'{tag} [{st}]'] += 1
                if tid in clips[lang]:
                    stats[lang][f'{tag} [{st}] (spoken)'] += 1
        rows.append(row)

    write_xlsx(rows, stats, texts)
    write_csvs(rows)
    print_summary(stats, rows)


def write_xlsx(rows, stats, texts):
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Font, PatternFill
        from openpyxl.utils import get_column_letter
    except ImportError:
        print('! openpyxl not installed - only the CSV files were written')
        return
    wb = Workbook()

    ws = wb.active
    ws.title = 'Overview'
    ws.column_dimensions['A'].width = 36
    ws.column_dimensions['B'].width = 78
    lines = [
        ('Thimbleweed Park - printed vs. spoken text audit', ''),
        ('', ''),
        ('Column "printed in game"', 'the string the engine shows: backslash escapes removed '
                                     '(" -> "), leading "(...)" direction and leading "{...}" '
                                     'command removed (both are consumed by the engine)'),
        ('Column "spoken by the voice (now)"', 'the exact string that is fed to piper today '
                                               '(tts_text.clean_text) - this is what the voice says'),
        ('Column "spoken (before the fix)"', 'what the voice said before the fix: the raw TSV '
                                             'string, so it read "backslash", "(sarcastic)", '
                                             '"ver te" ...'),
        ('', ''),
        ('"EN printed in game"', 'the original English text (recorded by the real actors)'),
        ('"spoken in game"', 'y = the line has a voice line in the original game (a "talkie"); '
                             'the others are only printed on screen'),
        ('"de clip"/"es clip"', 'y = a generated voice clip exists for that line'),
        ('', ''),
        ('Issues found (de)', ''),
    ]
    for k, v in stats['de'].most_common():
        lines.append((k, v))
    lines.append(('', ''))
    lines.append(('Issues found (es)', ''))
    for k, v in stats['es'].most_common():
        lines.append((k, v))
    lines += [
        ('', ''),
        ('Column "state"', 'fixed = the new pipeline no longer feeds the offending text to '
                           'piper; equivalent = piper says the symbol but the English line '
                           'says it too; check = piper says something the player does not hear '
                           'in English; open = still audible, needs a decision'),
        ('Note', 'the "direction" issue means the delivery direction in brackets is part of the '
                 'raw file only; the game removes it, the TTS voice used to read it out loud'),
        ('Note', '"censored-word": "ver*Biep*te" was spoken as "ver te" because the asterisks '
                 'were removed - the beep word itself is now spoken'),
        ('Note', 'the "symbol:" rows are silent on screen but piper says them out loud '
                 '("50%" -> "fifty percent", "$19.99" -> "dollar nineteen ninety nine")'),
        ('Note', '"voice-marker" (#F / #M) and "printf" (%d) hit mostly lines that are only '
                 'printed, never spoken'),
        ('', ''),
        ('Fix (2026-10-21)', 'tts_text.clean_text() now undoes the game escapes, drops the '
                             'leading delivery direction and the trailing "#F"/"#M" marker and '
                             'keeps the censored beep word. 3,772 clips were re-rolled '
                             '(1,465 de + 2,307 es).'),
    ]
    for a, b in lines:
        ws.append([a, b])
    ws.cell(row=1, column=1).font = Font(bold=True, size=13)

    def add_sheet(name, data):
        s = wb.create_sheet(name)
        s.append([h[1] for h in HEAD])
        for c in range(1, len(HEAD) + 1):
            cell = s.cell(row=1, column=c)
            cell.font = Font(bold=True)
            cell.fill = PatternFill('solid', fgColor='DDDDDD')
            cell.alignment = Alignment(vertical='top', wrap_text=True)
        for r in data:
            s.append([r.get(k, '') for k, _ in HEAD])
        widths = {'text_id': 10, 'actors': 18, 'talkie': 9, 'clip_de': 7, 'clip_es': 7}
        for i, (k, title) in enumerate(HEAD, start=1):
            s.column_dimensions[get_column_letter(i)].width = widths.get(k, 58)
        s.freeze_panes = 'A2'
        s.auto_filter.ref = s.dimensions
        return s

    add_sheet('compare (all lines)', rows)
    add_sheet('de issues', sorted([r for r in rows if r['de_issues']],
                                  key=lambda r: (not r['clip_de'], r['text_id'])))
    add_sheet('es issues', sorted([r for r in rows if r['es_issues']],
                                  key=lambda r: (not r['clip_es'], r['text_id'])))
    add_censored_sheet(wb, english_forms(texts))

    out = 'text_audit_de_es.xlsx'
    wb.save(out)
    print(f'wrote {out} ({os.path.getsize(out)} bytes)')


def add_censored_sheet(wb, english_of):
    """The table that turns the game's censored word into a milder word."""
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter
    from tts_censored import DE, ES, EN

    EN_LOWER = {k.lower(): v for k, v in EN.items()}

    s = wb.create_sheet('censored words')
    s.append(['The English game hides the word "fuck" behind a beep (*beep*, *beeping*, '
              '*beepface*, *Beepoff*, ...). The German translation replaced it with "Biep", '
              'the Spanish one with "biip" - a US convention that is not common in German '
              'or Spanish. The voices now say a milder word instead (tts_censored.py).'])
    s.cell(row=1, column=1).font = Font(bold=True)
    s.append([])
    s.append(['language', 'masked word in the text', 'said by the voice',
              'the English word it stands for', 'what the English line says'])
    for c in range(1, 6):
        cell = s.cell(row=3, column=c)
        cell.font = Font(bold=True)
        cell.fill = PatternFill('solid', fgColor='DDDDDD')
    row = 4
    for lang, table in (('de', DE), ('es', ES)):
        for key, mild in sorted(table.items()):
            s.cell(row=row, column=1, value=lang)
            s.cell(row=row, column=2, value=key)
            s.cell(row=row, column=3, value=mild)
            en = english_of.get(lang, {}).get(key, '')
            s.cell(row=row, column=4, value=en)
            s.cell(row=row, column=5, value=EN.get(en, EN_LOWER.get(en.lower(), '')))
            row += 1
    for i, w in enumerate((10, 24, 24, 30, 30), start=1):
        s.column_dimensions[get_column_letter(i)].width = w
    s.freeze_panes = 'A4'


def english_forms(texts):
    """masked word (de/es) -> the English masked word on the same line."""
    out = {'de': {}, 'es': {}}
    for lang in ('de', 'es'):
        counts = {}
        for tid, raw in texts[lang].items():
            en = texts['en'].get(tid, '')
            for m in re.finditer(r'\*([^*]*)\*', raw):
                inner = m.group(1)
                if not BEEP_RE.search(inner):
                    continue
                s = m.start()
                while s > 0 and raw[s - 1].isalnum():
                    s -= 1
                e = m.end()
                while e < len(raw) and raw[e].isalnum():
                    e += 1
                word = raw[s:e]
                for em in re.finditer(r'\*([^*]*)\*', en):
                    counts.setdefault(word, Counter())[em.group(0)] += 1
                    break
        for word, c in counts.items():
            out[lang][word] = c.most_common(1)[0][0].strip('*')
    return out


def write_csvs(rows):
    def dump(path, data):
        with open(path, 'w', newline='', encoding='utf-8-sig') as fh:
            w = csv.writer(fh)
            w.writerow([h[1] for h in HEAD])
            for r in data:
                w.writerow([r.get(k, '') for k, _ in HEAD])
        print(f'wrote {path} ({len(data)} rows)')

    dump('text_audit_de_es.csv', rows)
    dump('text_audit_flags.csv', sorted([r for r in rows if r['de_issues'] or r['es_issues']],
                                         key=lambda r: (not (r['clip_de'] or r['clip_es']), r['text_id'])))


def print_summary(stats, rows):
    for lang in TTS_LANGS:
        print(f'--- {lang}')
        for k, v in stats[lang].most_common():
            print(f'   {k:28} {v}')
    n_clip = sum(1 for r in rows if r['clip_de'] or r['clip_es'])
    print(f'text ids: {len(rows)}; with a generated clip: {n_clip}')


if __name__ == '__main__':
    main()
