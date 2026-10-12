# Thimbleweed Park — Language Voice Mod toolkit

Generates and installs **German** and **Spanish** voice audio for the Android
version of [Thimbleweed Park](https://thimbleweedpark.com), driven by the
in-game language selection: pick *Deutsch* → German voices, *Español* →
Spanish voices, English → the original recordings. Every character gets their
own distinct synthetic voice (male characters male voices, female characters
female voices — determined automatically from the pitch of the original
English recordings).

> **What this repository contains:** only the tooling. It does **not** contain
> any game data (GGPack/OBB/APK), the game's copyrighted text, or the
> generated audio. You must own the game; running the pipeline produces the
> voice files locally from your own copy.

## How it works

The Android game data file (`.obb`) is a single **GGPack** archive — a custom
container with a binary-JSON file table and an obfuscated XOR stream
(reverse-engineered from `libThimbleweedPark.so`; the older PC releases are
covered by the public [ScummVM `twp` engine](https://github.com/scummvm/scummvm/tree/master/engines/twp)).
The engine looks up every spoken line as `<ACTOR>_<TEXTID>.ogg` with **no
language component** — the reason all languages play the English recordings.

This toolkit:

1. **Patches the engine** (`so_locate.py` + `so_patch.py`): finds the talkie /
   lip-sync filename lookups in `libThimbleweedPark.so` automatically (any
   build), injects a small code patch that appends the current game language
   to the lookup (`RAY_01234.ogg` → `RAY_01234_de.ogg`), with graceful
   fallback to the original name. The patch is verified by emulating the
   patched code *through the engine's own printf implementation*
   (`verify_cave.py`).
2. **Measures every actor's gender** (`f0.py`): fundamental frequency of the
   actor's original English lines classifies the voice as male or female —
   including corrections for characters whose performance pitch is misleading
   (shrill clown, squeaky pigeon brothers, dog…).
3. **Assigns a distinct voice per character** (`assign_voices.py`): from
   [Piper](https://github.com/rhasspy/piper) neural voices per language —
   including a 236-speaker multi-speaker German model — plus per-character
   pitch/speed variants, so you can hear *who* is speaking.
4. **Synthesizes all lines** (`tts_build.py`): reads each language's shipped
   subtitle table (`ThimbleweedText_de.tsv` / `_es.tsv`) from your own OBB,
   strips stage directions, synthesizes with the assigned voice, matches
   loudness to the English original, and derives lip-sync by scaling the
   English timings.
5. **Repacks** (`ggpack_write.py`, `build_mod.py`, `repack.py`): appends the
   new audio to a copy of your OBB (originals untouched), patches the APK's
   engine library, and signs the result.

## Requirements

- python3 with `numpy`, `piper-tts`, `capstone`, `unicorn`, `pyaxmlparser`
- `ffmpeg` (with the `rubberband` filter), `keytool`, Android build-tools
  (`apksigner`, `zipalign`), `adb`

## Pipeline

```bash
# 0. back up your installed game (phone connected, USB debugging on)
./backup_phone.sh

# 1. patch the engine library from your own APK
python3 so_patch.py <extracted libThimbleweedPark.so> patched_arm64.so
python3 verify_cave.py patched_arm64.so <original .so>   # END-TO-END: PASS

# 2. measure voices and build the actor → voice assignment
python3 voice_survey.py            # measures all Piper voice candidates
python3 actor_f0b.py               # measures all actors' English-line pitch
python3 assign_voices.py           # writes cache/voice_assign.json

# 3. synthesize ~30k clips (German + Spanish), ~1-2 h on 20 cores
python3 tts_build.py 0 20

# 4. build modded OBB + APK, sign, install, push OBB
python3 build_mod.py phone_backup_*/base.apk \
        phone_backup_*/main.*.obb --no-embed-obb
adb install dist_from_phone/ThimbleweedPark-mod-<vc>.apk
adb push dist_from_phone/main.*.obb \
    /storage/emulated/0/Android/obb/com.terribletoybox.thimbleweedparkandroid/
```

## Extending to other languages

The engine supports text languages `de es fr it ru`. To add e.g. Italian
voices: download an Italian Piper voice, extend the pools in
`assign_voices.py`, add `it` to the language tuples in `tts_build.py` and the
patch suffix list in `so_patch.py` (`SUFFIXES`), and regenerate. The engine
side needs no further changes — it appends whatever the game language is.

## License

Code: LGPL-3.0 (see `LICENSE`).

Note: this is a fan project, not affiliated with Terrible Toybox. Requires an
owned copy of the game. For personal use; don't distribute game data or the
generated audio, which derives from the game's copyrighted translations.
