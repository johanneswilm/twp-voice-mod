import re, json, random, collections, os, tempfile, wave
import numpy as np
from ggpack3 import GGPack
from f0 import decode, median_f0

pack = GGPack('main.65.com.terribletoybox.thimbleweedparkandroid.obb')
pat = re.compile(r'^([A-Z0-9]+)_(\d{5})\.ogg$')
by_actor = collections.defaultdict(list)
for n in pack.entries:
    m = pat.match(n)
    if m: by_actor[m.group(1)].append(n)

def frames_f0(pcm, rate=16000, fmin=60.0, fmax=400.0):
    x = pcm.astype(np.float32) / 32768.0
    win = int(rate * 0.04); hop = win // 2
    lag_min = int(rate / fmax); lag_max = int(rate / fmin)
    f0s = []
    if len(x) < win * 3: return f0s
    rms = np.sqrt(np.convolve(x ** 2, np.ones(win) / win, 'same'))
    gate = np.percentile(rms[rms > 0], 55) * 0.4
    for start in range(0, len(x) - win, hop):
        if rms[start + win // 2] < gate: continue
        fr = x[start:start + win]; fr = fr - fr.mean()
        ac = np.correlate(fr, fr, 'full')[win - 1:]
        if ac[0] <= 0: continue
        ac /= ac[0]
        seg = ac[lag_min:lag_max]
        p = int(np.argmax(seg)) + lag_min
        v = ac[p]
        if v < 0.55: continue
        # octave correction: if a strong peak exists at 2*p, prefer it (true lower f0)
        p2 = 2 * p
        if p2 < lag_max and ac[p2] > 0.9 * v:
            p = p2; v = ac[p2]
            p3 = 3 * p
            if p3 < lag_max and ac[p3] > 0.95 * v: p = p3
        a, b, c = ac[p - 1], ac[p], ac[p + 1]
        d = a - 2 * b + c
        if d != 0: p = p + np.clip(0.5 * (a - c) / d, -1, 1)
        f0 = rate / p
        if fmin <= f0 <= fmax: f0s.append(f0)
    return f0s

result = {}
for actor in sorted(by_actor):
    clips = [c for c in by_actor[actor]]
    random.Random(2).shuffle(clips)
    clips = clips[:80]
    allf = []
    tmp = f'/tmp/f0b_{os.getpid()}.ogg'
    for c in clips:
        open(tmp, 'wb').write(pack.read(c))
        pcm = decode(tmp)
        if pcm is None or len(pcm) < 24000: continue   # >1.5 s
        allf.extend(frames_f0(pcm))
    os.unlink(tmp)
    if len(allf) < 30:
        result[actor] = {'f0': 0.0, 'n': len(allf), 'gender': '?', 'clips': len(clips)}
    else:
        f0 = float(np.percentile(allf, 30))
        result[actor] = {'f0': round(f0, 1), 'n': len(allf), 'gender': 'f' if f0 >= 170 else 'm', 'clips': len(clips)}
    print(f"{actor:15s} f0={result[actor]['f0']:6.1f} {result[actor]['gender']} frames={len(allf):5d}", flush=True)
json.dump(result, open('cache/actor_f0b.json', 'w'), indent=1)
print("DONE")
