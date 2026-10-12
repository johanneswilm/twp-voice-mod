"""Synthesize a fixed sentence with every candidate voice/speaker and measure f0."""
import json
import numpy as np
from piper import PiperVoice, SynthesisConfig
from f0 import median_f0

DE = "Unser Chef ist seit zwanzig Jahren hier beschäftigt und kennt jede Geschichte dieser Stadt."
ES = "Nuestro jefe trabaja aquí desde hace veinte años y conoce todas las historias de la ciudad."


def measure(name, text, speaker=None):
    v = PiperVoice.load(f'voices/{name}.onnx')
    cfg = SynthesisConfig(speaker_id=speaker) if speaker is not None else SynthesisConfig()
    chunks = list(v.synthesize(text, syn_config=cfg))
    rate = chunks[0].sample_rate
    pcm = b"".join(c.audio_int16_bytes for c in chunks)
    a = np.frombuffer(pcm, dtype=np.int16)
    return round(median_f0(a, rate), 1)


out = {}
jobs = [("de_DE-thorsten-high", DE), ("de_DE-thorsten-medium", DE), ("de_DE-pavoque-low", DE),
         ("de_DE-karlsson-low", DE), ("de_DE-kerstin-low", DE), ("de_DE-ramona-low", DE)]
jobs += [("es_MX-claude-high", ES), ("es_AR-daniela-high", ES), ("es_ES-davefx-medium", ES),
         ("es_MX-ald-medium", ES), ("es_ES-sharvard-medium", ES),
         ("es_ES-mls_10246-low", ES), ("es_ES-mls_9972-low", ES)]
for name, txt in jobs:
    if "mls" in name or "sharvard" in name:
        cfgj = json.load(open(f"voices/{name}.onnx.json"))
        ids = sorted(cfgj.get("speaker_id_map", {}).values())
        if len(ids) > 4:
            ids = ids[0:40]
        for s in ids:
            try:
                f = measure(name, txt, s)
            except Exception as e:
                print(name, s, "ERR", e, flush=True)
                continue
            g = "f" if f >= 165 else "m"
            out[f"{name}|{s}"] = [f, g]
            print(name, s, f, g, flush=True)
    else:
        f = measure(name, txt)
        g = "f" if f >= 165 else "m"
        out[name] = [f, g]
        print(name, "-", f, g, flush=True)
json.dump(out, open("cache/voice_f0.json", "w"), indent=1)
print("SURVEY DONE")
