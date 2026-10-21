"""Original deterministic shutter integration of RGBA samples in linear light."""
import io

import numpy as np
from PIL import Image


def sample_times(frame, count, samples, shutter):
    if samples == 1 or shutter == 0:
        return [float(frame)]
    return [min(count-1, max(0., frame + ((i+.5)/samples-.5)*shutter)) for i in range(samples)]


def average_png(samples):
    """Premultiply linear RGB by alpha, average, then return straight-alpha sRGB."""
    total = None; count = 0
    for data in samples:
        with Image.open(io.BytesIO(data)) as im:
            rgba = np.asarray(im.convert('RGBA'), dtype=np.float32)/255
        rgb, alpha = rgba[..., :3], rgba[..., 3:4]
        rgb = np.where(rgb <= .04045, rgb/12.92, ((rgb+.055)/1.055)**2.4)
        value = np.concatenate((rgb*alpha, alpha), axis=-1)
        if total is None: total = value
        else: total += value
        count += 1
    if not count: raise ValueError('At least one shutter sample is required')
    total /= count; alpha = total[..., 3:4]
    rgb = np.divide(total[..., :3], alpha, out=np.zeros_like(total[..., :3]), where=alpha>0)
    rgb = np.where(rgb <= .0031308, rgb*12.92, 1.055*rgb**(1/2.4)-.055)
    rgba = np.round(np.clip(np.concatenate((rgb, alpha), axis=-1), 0, 1)*255).astype(np.uint8)
    out = io.BytesIO(); Image.fromarray(rgba, 'RGBA').save(out, format='PNG'); return out.getvalue()
