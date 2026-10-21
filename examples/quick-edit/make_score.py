"""Reproduce the original eight-second score. No samples or model calls."""
from pathlib import Path
import wave
import numpy as np


def main():
    rate = 44100
    t = np.arange(rate * 8) / rate
    out = np.zeros_like(t)
    rng = np.random.default_rng(42)
    for beat in range(16):
        u = t - beat * .5
        gate = (u >= 0) & (u < .4)
        out += .42 * np.sin(2*np.pi*(46*u + 8*(1-np.exp(-30*np.maximum(u, 0))))) * np.exp(-14*np.maximum(u, 0)) * gate
        for half in (0, .25):
            v = u - half
            out += .035 * rng.normal(size=len(t)) * np.exp(-70*np.maximum(v, 0)) * ((v >= 0) & (v < .08))
        freq = [130.8128, 155.5635, 174.6141, 116.5409][beat // 4]
        out += .12 * np.sin(2*np.pi*freq*u) * np.exp(-7*np.maximum(u, 0)) * gate
    out *= np.minimum(1, t/.015) * np.minimum(1, (8-t)/.15)
    pcm = (out.clip(-.9, .9)*32767).astype('<i2')
    target = Path(__file__).parent / 'assets' / 'orbit.wav'
    with wave.open(str(target), 'wb') as wav:
        wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(rate); wav.writeframes(pcm.tobytes())


if __name__ == '__main__': main()
