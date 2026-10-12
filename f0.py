"""Measure fundamental frequency (f0) of audio to classify voice gender.

Usage: f0.py <wav or ogg file...>   -> prints median f0 per file
Library use: median_f0(pcm_int16, rate) -> float Hz or 0
"""
import subprocess
import sys
import tempfile
import wave

import numpy as np


def decode(path, rate=16000):
    out = tempfile.NamedTemporaryFile(suffix='.wav', delete=False)
    out.close()
    r = subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', path,
                        '-ar', str(rate), '-ac', '1', '-c:a', 'pcm_s16le', out.name],
                       capture_output=True)
    if r.returncode != 0:
        return None
    with wave.open(out.name, 'rb') as wf:
        data = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16)
    import os
    os.unlink(out.name)
    return data


def median_f0(pcm, rate=16000, fmin=60.0, fmax=350.0):
    x = pcm.astype(np.float32) / 32768.0
    if len(x) < rate // 2:
        return 0.0
    win = int(rate * 0.04)          # 40 ms frames
    hop = win // 2
    lag_min = int(rate / fmax)
    lag_max = int(rate / fmin)
    f0s = []
    rms_all = np.sqrt(np.convolve(x ** 2, np.ones(win) / win, 'same'))
    gate = np.percentile(rms_all[rms_all > 0], 60) * 0.5
    for start in range(0, len(x) - win, hop):
        if rms_all[start + win // 2] < gate:
            continue
        frame = x[start:start + win]
        frame = frame - frame.mean()
        ac = np.correlate(frame, frame, 'full')[win - 1:]
        if ac[0] <= 0:
            continue
        ac = ac / ac[0]
        seg = ac[lag_min:lag_max]
        peak = np.argmax(seg) + lag_min
        # simple sub-bin refinement via parabolic interpolation
        if 1 <= peak - lag_min < len(seg) - 1:
            a, b, c = ac[peak - 1], ac[peak], ac[peak + 1]
            denom = a - 2 * b + c
            if denom != 0:
                shift = 0.5 * (a - c) / denom
                peak = peak + np.clip(shift, -1, 1)
        f0 = rate / peak
        if fmin <= f0 <= fmax:
            f0s.append(f0)
    if len(f0s) < 5:
        return 0.0
    return float(np.median(f0s))


def file_f0(path):
    pcm = decode(path)
    if pcm is None or len(pcm) == 0:
        return 0.0
    return median_f0(pcm)


if __name__ == '__main__':
    for p in sys.argv[1:]:
        print(f"{file_f0(p):6.1f} Hz  {p}")