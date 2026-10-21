"""Milder German/Spanish words for the game's censored words.

The original English text hides the word "fuck" behind a beep: *beep*,
*beeping*, *beepface*, *beephole*, *Beepoff*, *fucker* -> *Beeper* ...
The German translation replaced the same word with "Biep", the Spanish one
with "biip" - both of them are the beep, a censorship convention that is
common in the US but not in German/Spanish speaking countries.

The voices should not beep.  This module maps every masked word that occurs
in the German/Spanish files to a milder word with the same meaning:

    de:  ver*Biep*te  ->  verdammte        (fucking -> verdammt)
    de:  *Biep*loch   ->  Muschi           (fuckhole -> Muschi)
    es:  *biip*       ->  mierda           (fuck -> mierda)
    es:  *gilibiips*  ->  gilipollas

The table is keyed by the masked word exactly as it appears in the TSV
(the asterisks included).  Longer keys are tried first, so that
"ver *Biep*tes" wins over "ver*Biep*t".
"""
import re

# the trailing "#F"/"#M" marker of the translation files (not text, but the
# German/Spanish files carry it at the end of the line)
VOICE_MARKER_RE = re.compile(r'#(?:F|M|Z)\s*$')

# --- German ---------------------------------------------------------------
# "fuck" as an intensifier -> "verdammt" (and its case endings)
DE = {
    # intensifier / adjective
    'ver *Biep*tes': 'verdammtes',
    'ver *Biep*tem': 'verdammtem',
    'ver*Biep*tes': 'verdammtes',
    'ver*Biep*ten': 'verdammten',
    'ver*Biep*te': 'verdammte',
    'ver*Biep*ter': 'verdammter',
    'ver*Biep*tem': 'verdammtem',
    'ver*Biep*t': 'verdammt',
    'Ver*Biep*te': 'Verdammte',
    'Ver*Biep*ter': 'Verdammter',
    'Ver*Biep*': 'Verpiss',
    'ver*Biep*': 'verdammt',
    '*Biep*enden': 'verdammten',
    '*Biep*ender': 'verdammter',
    '*Biep*endes': 'verdammtes',
    '*Biep*endem': 'verdammtem',
    '*Biep*ende': 'verdammte',
    '*Biep*end': 'verdammt',
    'Groß*Biep*end': 'Riesending',
    'ge*Biep*ten': 'verdammten',
    'ge*Biep*ter': 'verdammter',
    'ge*Biep*tes': 'verdammtes',
    'ge*Biep*te': 'verdammte',
    'ge*Biep*t': 'verdammt',
    'be*Biep*te': 'verdammte',
    '*Biep*igen': 'verdammten',
    '*Biep*iger': 'verdammter',
    '*Biep*iges': 'verdammtes',
    '*Biep*ige': 'verdammte',
    '*Biep*ig': 'verdammt',
    'un*Biep*ig': 'unverdammt',
    '*Biep*haft': 'total',
    '*Biep*erlich': 'scheisslich',
    '*Biep*lich': 'scheisslich',
    '*Biep*mals': 'verdammt',
    '*Biep*gen': 'verdammten',
    '*Biep*es': 'verdammtes',
    '*Biep*tes': 'verdammtes',
    '*Biep*tem': 'verdammtem',
    '*Biep*tastischen': 'wahnsinnigen',
    'über*Biep*kandidelt': 'überheblich',
    # people
    '*Biep*ern': 'Idioten',
    '*Biep*ers': 'Idioten',
    '*Biep*er': 'Idiot',
    '*Biep*ler': 'Idiot',
    '*Beeper*': 'Pieps',
    '*Beephole*': 'Muschi',
    'Hosen*Biep*er': 'Hosenidiot',
    '*Biep*gesichter': 'Scheißgesichter',
    '*Biep*gesicht': 'Scheißgesicht',
    'Mc*Biep*face': 'McScheißgesicht',
    '*Biep*backe': 'Dummkopf',
    '*Biep*köpfe': 'Dummköpfe',
    '*Biep*kopf': 'Dummkopf',
    '*Biep*dumme': 'Dummkopf',
    # the rest
    '*Biep*boter': 'Mistroboter',
    '*Biep*stadt': 'Scheißstadt',
    '*Biep*laden': 'Scheißladen',
    '*Biep*löcher': 'Muschis',
    '*Biep*loch': 'Muschi',
    '*Biep*nase': 'Scheißnase',
    'Hunde*Biep*': 'Hundescheiß',
    'Ratten*Biep*': 'Rattenscheiß',
    'Doppel*Biep*': 'Doppelscheiß',
    'Thimble*Biep*': 'ThimbleScheiß',
    'ver*Biep*en': 'verpissen',
    '*Biep*en': 'bestechen',
    '*Biep*dich': 'Verpiss',
    '*Biep*t': 'Scheiß',
    '*Biep*e': 'Scheiß',
    '*Biep*s': 'Scheiß',
    '*Biep*': 'Scheiß',
    '*BIEP*': 'SCHEISS',
    '*Biiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiep*': 'Scheiss',
    # sound effects (not profanity)
    'Ver*Bloop*te': 'Verploppte',
    '*Bloop*': 'Plopp',
    '*Bliep*': 'Piep',
}

# --- Spanish --------------------------------------------------------------
ES = {
    '*biiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiip*': 'mierda',
    '*biiiiiiiiiiiiiiiiiiiiiiip*': 'mierda',
    # intensifier / adjective
    '*biipamente*': 'jodidamente',
    '*biipmente*': 'jodidamente',
    '*biipado*': 'jodido',
    '*biipidos*': 'jodidos',
    '*biipido*': 'jodido',
    '*biipidas*': 'jodidas',
    '*biipida*': 'jodida',
    '*biipó*': 'jodió',
    '*biipo*': 'cago',
    '*biipen*': 'joda',
    '*Biipen*': 'Joda',
    '*BIIPEN*': 'JODA',
    '*biiperme*': 'joderme',
    '*biiper*': 'mierda',
    '*biipan*': 'joda',
    '*biipe*': 'joda',
    # people
    '*biiponazo*': 'capullo',
    '*biipote*': 'idiota',
    '*biipón*': 'capullo',
    '*Biipler*': 'capullo',
    '*biipullo*': 'mierdilla',
    '*biipona*': 'maldita',
    '*biiponesa*': 'maldita',
    '*biipísima*': 'malísima',
    '*biipisima*': 'malísima',
    '*malbiipada*': 'maldita',
    # the rest
    '*gilibiips*': 'gilipollas',
    '*carabiips*': 'carajos',
    '*soplabiips*': 'soplapollas',
    '*chupabiips*': 'chupapollas',
    '*tocabiips*': 'tocapollas',
    '*robobiips*': 'robopollas',
    '*hijobiips*': 'hijomierdas',
    '*tontobiips*': 'tontomierda',
    '*biipones*': 'mierdas',
    '*biipas*': 'mierdas',
    '*biips*': 'mierdas',
    '*biipete*': 'culo',
    'Thimble*biip*': 'Thimblemierda',
    '*biip*': 'mierda',
    '*Biip*': 'Mierda',
    '*BIIP*': 'MIERDA',
    # sound effects (not profanity)
    '*bluupes*': 'plofes',
    '*bluup*': 'plof',
    '*bliip*': 'pi',
}

TABLES = {'de': DE, 'es': ES}

# The English forms and the word they hide ("the beep" -> "fuck")
EN = {
    'beep': 'fuck', 'Beep': 'Fuck', 'beeping': 'fucking', 'Beeping': 'Fucking',
    'beeped': 'fucked', 'beeps': 'fucks', 'beeper': 'fucker', 'Beeper': 'Fucker',
    'Beepler': 'Fucker', 'beepface': 'fuckface', 'beepface!': 'fuckface!',
    'beephole': 'fuckhole', 'Beephole': 'Fuckhole', 'Beephole.': 'Fuckhole.',
    'beepholes': 'fuckholes', 'beephead': 'fuckhead', 'Beephead': 'Fuckhead',
    'beepoff': 'fuck off', 'Beepoff': 'Fuck off', 'Beepoff!': 'Fuck off!',
    'beepwit': 'fuckwit', 'beepwipe': 'fuckwipe', 'beepwads': 'fuckwads',
    'beeptastic': 'fucktastic', 'beepup': 'fuckup', 'Beepus': 'Fuckus',
    'Beepbots': 'Fuckbots', 'bloop': '(sound)', 'blooping': '(sound)',
    'bleep': '(sound)', 'Beeeeeeeeeeeeeeeeeeeeeeeeep': 'Fuuuuuck',
    'Beeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeep': 'Fuuuuuck',
}

# --- context rules ---------------------------------------------------------
# "Was zur *Biep*" -> "Was zur Hölle" ("Scheiß" does not work after "zur")
DE_ZUR = re.compile(r'\b(zur)(\s+)\*Biep\*(?![a-zA-Zäöüß])', re.IGNORECASE)
# "*Biep* dich" / "*Biep* mich" -> "Verpiss dich" (the mask is not part of a word)
DE_DICH = re.compile(r'(?<![a-zA-Zäöüß])\*Biep\*(?=\s+(dich|mich)\b)', re.IGNORECASE)
# "den *Biep* Fahrstuhl" -> "den verdammten Fahrstuhl" (the article gives
# gender and case, so the adjective ending can be derived from it)
DE_ARTICLE_ENDING = {
    'der': 'er', 'die': 'e', 'das': 'e', 'den': 'en', 'dem': 'en', 'des': 'en',
    'ein': 'er', 'eine': 'e', 'einen': 'en', 'einem': 'em', 'eines': 'es',
    'einer': 'en',
    'kein': 'er', 'keine': 'e', 'keinen': 'en', 'keinem': 'em',
    'ihr': 'er', 'ihrem': 'em', 'ihren': 'en', 'ihre': 'e', 'ihrigen': 'en',
    'mein': 'er', 'meine': 'e', 'meinen': 'en', 'meinem': 'em', 'meines': 'es',
    'diese': 'e', 'diesen': 'en', 'diesem': 'en', 'dieses': 'e',
    'jener': 'er', 'jene': 'e', 'jenen': 'en', 'jenem': 'en', 'jenes': 'e',
    'alle': 'e', 'allen': 'en', 'viele': 'e', 'vielen': 'en',
    'seine': 'e', 'seinen': 'en', 'seinem': 'em', 'seiner': 'er',
    'welche': 'e', 'welchen': 'en', 'welchem': 'en', 'welcher': 'er',
    'unsere': 'e', 'unseren': 'en', 'unser': 'er', 'unserem': 'em',
    'jede': 'e', 'jeden': 'en', 'jeder': 'er', 'jedes': 'e',
    'andere': 'e', 'anderen': 'en', 'anderer': 'er', 'anderes': 'e',
}
DE_ARTICLE = re.compile(r'\b(' + '|'.join(DE_ARTICLE_ENDING) + r')(\s+)\*Biep\*(?![a-zA-Zäöüß])',
                        re.IGNORECASE)
# the plain (unmasked) beep words: those are sound effects, German says "Piep"
DE_PLAIN = [('Biepen', 'Piepen'), ('Bieper', 'Piepser'), ('Biep', 'Piep')]

# "un *biip* biip de censura" -> "una mierda de censura"
ES_PHRASES = [('un *biip* biip de censura', 'una mierda de censura')]
# the mask as an adjective: "el *biip* payaso" -> "el maldito payaso"
ES_ADJ_M = re.compile(r'\b(el|un|este|ese|los)\s+\*biip\*(?=\s+[a-záéíóúñ¿¡])', re.IGNORECASE)
ES_ADJ_F = re.compile(r'\b(la|una|esta|esa|las)\s+\*biip\*(?=\s+[a-záéíóúñ¿¡])', re.IGNORECASE)


def _compile(table):
    keys = sorted(table, key=len, reverse=True)
    rx = re.compile('|'.join(re.escape(k) for k in keys))
    return rx, table


_COMPILED = {lang: _compile(t) for lang, t in TABLES.items()}


def replace_censored(text, lang):
    """Replace the masked profanity with the milder local word."""
    if lang == 'de':
        text = DE_ZUR.sub(r'\1\2Hölle', text)
        text = DE_DICH.sub('Verpiss', text)
        text = DE_ARTICLE.sub(
            lambda m: f'{m.group(1)}{m.group(2)}verdammt{DE_ARTICLE_ENDING[m.group(1).lower()]}',
            text)
    elif lang == 'es':
        for phrase, mild in ES_PHRASES:
            text = text.replace(phrase, mild)
        text = ES_ADJ_M.sub(lambda m: f'{m.group(1)} maldito', text)
        text = ES_ADJ_F.sub(lambda m: f'{m.group(1)} maldita', text)
    table = TABLES.get(lang)
    if table:
        rx, table = _COMPILED[lang]
        text = rx.sub(lambda m: table[m.group(0)], text)
    if lang == 'de':
        # the plain (unmasked) beep words are sound effects: German says "Piep"
        for plain, mild in DE_PLAIN:
            text = re.sub(r'\b' + plain + r'\b', mild, text)
    return text


def subtitle_text(raw, lang):
    """The text as the game should show it.

    Same as the raw translation, but the censored word is a real (milder)
    word instead of "Biep"/"biip", so the subtitle matches what the voice
    says.  Only the text of the localisation file is touched - the engine
    commands ({...}) and the stage directions (*...*) stay as they are.
    """
    return replace_censored(raw, lang)
