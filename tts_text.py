"""Text rules for the German/Spanish TTS voices.

The localisation files (ThimbleweedText_{de,es}.tsv) do NOT contain the
strings the game shows and the characters speak.  The engine transforms them
before they reach the screen:

* `Text::loadLanguageTable` (libThimbleweedPark.so) drops every backslash
  while loading the TSV, so `\"` is printed as `"` and `\n` as `n`.
* `Obtor::parseSayLine` consumes a leading `(...)` delivery direction and a
  leading `{...}` engine command - neither is shown nor spoken.

The TTS pipeline used to feed the *raw* TSV string to piper, so the voices
read things the player never sees:

  * the backslash of `\"`  -> "Wechsel" / "backslash" (German voices)
  * the leading `(...)`    -> "sarcastic", "dont_translate", "fast", ...
  * the censored beep word -> "ver*Biep*te" was spoken as "ver te"
  * the trailing "#F"/"#M" -> "Nummer Eff" (a translation marker, not text)

`clean_text()` below is the corrected version and is used by tts_build.py,
asr_sweep.py and tts_text_audit.py.  `clean_text_legacy()` is the old
behaviour, kept for the audit (it shows what the voices said before).
"""
import re

from tts_censored import replace_censored

TAG_RE = re.compile(r'\{[^}]*\}')
STAR_RE = re.compile(r'\*([^*]*)\*')
LEAD_PAREN = re.compile(r'^\s*\([^)]*\)')
LEAD_BRACE = re.compile(r'^\s*\{[^}]*\}')
TRADEMARK_RE = re.compile(r'[™©®]')
VOICE_MARKER_RE = re.compile(r'#(?:F|M|Z)\s*$')
PRINTF_PLACEHOLDER_RE = re.compile(r'%(?:\d+\$)?[a-zA-Z]')
# the censored beep word of the game: "Biep", "biipones", "beeping", "Bloop" ...
BEEP_RE = re.compile(r'(?i)(eep|iep|iip|oop|uup)')


def game_unescape(s):
    """What the engine does with the backslashes while loading the TSV."""
    return re.sub(r'\\(.)', r'\1', s)


def _strip_leading(t):
    """Remove the leading direction/command, like the engine does.

    The engine consumes a leading "(...)" and a leading "{...}" (in that
    order, and they can follow each other, e.g. "(mad){tv_chuck_angry}...").
    A line that consists of nothing but a direction keeps its content.
    """
    orig = t
    prev = None
    while prev != t:
        prev = t
        t = LEAD_PAREN.sub(' ', t)
        t = LEAD_BRACE.sub(' ', t)
    if not t.strip() and LEAD_PAREN.match(orig):
        t = orig
    return t


def game_text(raw, lang=None):
    """The string as the game prints it (subtitle / talkie text).

    The mod ships the German/Spanish localisation file with the censored
    word replaced by a mild word (tts_censored.subtitle_text), so the
    subtitle matches what the voice says.
    """
    t = game_unescape(raw)
    if lang:
        t = replace_censored(t, lang)
    t = _strip_leading(t)
    return re.sub(r'\s+', ' ', t).strip()


def _apply_masks(t):
    """Handle every "*...*" span on its own.

    The censored beep word ("*Biep*") is spoken by the actors, a stage
    direction ("*Seufz*") is not.  A beep word that follows a word character
    is separated from it ("ver*Biep*te" -> "ver Biepte"), otherwise piper
    mangles the compound.
    """
    out = []
    pos = 0
    for m in re.finditer(r'\*([^*]*)\*', t):
        out.append(t[pos:m.start()])
        inner = m.group(1)
        if BEEP_RE.search(inner):
            if out and out[-1] and out[-1][-1].isalnum():
                out.append(' ')
            out.append(inner)
        else:
            out.append(' ')
        pos = m.end()
    out.append(t[pos:])
    return ''.join(out)


def _finish(t):
    t = t.replace('\n', ' ').replace('\r', ' ')
    t = re.sub(r'\s+', ' ', t).strip()
    if not re.search(r'\w', t):
        return ''
    return t


def clean_text(t, lang):
    """The text the voice should say."""
    t = _strip_leading(game_unescape(t))
    # the censored word ("*Biep*", "*biip*") becomes a milder local word
    t = replace_censored(t, lang)
    t = _apply_masks(t)                    # "*Seufz*" (stage direction) -> dropped
    t = TRADEMARK_RE.sub('', t)
    t = VOICE_MARKER_RE.sub('', t)         # trailing "#F" / "#M"
    return _finish(t)


def clean_text_legacy(t):
    """The text the voices were fed before the fix (tts_build.clean_text)."""
    t = TAG_RE.sub(' ', t)
    t = re.sub(r'\*[^*]*\*', ' ', t)
    t = re.sub(r'[™©®]', '', t)
    return _finish(t)
