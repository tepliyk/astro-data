"""Hubble-inspired (gold/blue) palette from duo-band Ha + OIII data.

A purely mathematical remapping of the two existing channels, no generative AI.
Brightness comes from both channels, the hue only from the OIII share in each pixel,
so the core does not blow out to white the way a linear channel mix (or classic Foraxx) can.
This is not SHO: there is no SII channel, and the colours show a chosen mapping of the
independently stretched signals, not quantitative line ratios or gas abundances.

Inputs are LINEAR, STARLESS mono FITS for Ha and OIII (same size, already background-extracted
and denoised), plus an optional linear RGB stars-only FITS from your star removal tool.

    python hubble_map.py --ha Ha.fits --oiii OIII.fits --stars stars.fits --out rosette

Writes <out>_16bit.tiff (for further editing) and <out>.jpg (preview), plus <out>_params.json.
Defaults are the exact settings of the Rosette v2: https://app.astrobin.com/i/u0bd2k

Requirements: pip install numpy scipy astropy tifffile pillow
Author: Kostia Tepliy (Nebo Blyzhche), free to use and modify.
"""
import argparse
import json

import numpy as np
import tifffile
from astropy.io import fits
from PIL import Image
from scipy.ndimage import gaussian_filter

ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument('--ha', required=True, help='linear starless Ha, mono FITS')
ap.add_argument('--oiii', required=True, help='linear starless OIII, mono FITS')
ap.add_argument('--stars', help='linear stars-only RGB FITS (optional)')
ap.add_argument('--out', default='hubble', help='output file prefix')
ap.add_argument('--flip', action='store_true', help='flip vertically (some tools write FITS bottom-up)')
# stretch
ap.add_argument('--lo', type=float, default=2, help='black point percentile for normalisation')
ap.add_argument('--ha_mid', type=float, default=0.30, help='where the 75th percentile of Ha lands after stretch')
ap.add_argument('--o_boost', type=float, default=0.85, help='OIII target = ha_mid * o_boost')
# colour
ap.add_argument('--lw', type=float, default=0.55, help='weight of Ha in brightness (rest is OIII)')
ap.add_argument('--lum_m', type=float, default=0.47, help='extra midtone on brightness: <0.5 brighter')
ap.add_argument('--t_lo', type=float, default=14, help='OIII share percentile that is pure gold')
ap.add_argument('--t_hi', type=float, default=94, help='OIII share percentile that is pure blue')
ap.add_argument('--gold', type=float, nargs=3, default=[1.0, 0.60, 0.22])
ap.add_argument('--blue', type=float, nargs=3, default=[0.36, 0.66, 1.0])
ap.add_argument('--neutral_lo', type=float, default=0.12, help='below this brightness colour fades to grey (keeps background neutral)')
# finish
ap.add_argument('--lc', type=float, default=0.35, help='large-scale local contrast')
ap.add_argument('--sat', type=float, default=1.12)
ap.add_argument('--ped', type=float, default=0.06, help='neutral background pedestal, avoids clipped blacks')
ap.add_argument('--stars_amt', type=float, default=0.8)
ap.add_argument('--star_m', type=float, default=0.03, help='midtone for stars: lower is brighter')
ap.add_argument('--star_sat', type=float, default=0.45, help='star colour saturation, 0 = white stars')
a = ap.parse_args()


def load(path):
    d = fits.getdata(path).astype(np.float64)
    return d[..., ::-1, :] if a.flip else d


def norm(x, lo, hi=99.97):
    b, t = np.percentile(x, lo), np.percentile(x, hi)
    return np.clip((x - b) / (t - b), 0, 1)


def mtf(x, m):
    """Midtones transfer function, same as STF/histogram transformation in Siril and PixInsight."""
    return ((m - 1) * x) / ((2 * m - 1) * x - m)


def stretch(x, target):
    """Non-linear stretch that puts the 75th percentile (faint nebula level) at `target`."""
    ref = max(np.percentile(x, 75), 1e-6)
    m = np.clip(mtf(ref, target), 1e-5, 0.5)
    return np.clip(mtf(x, m), 0, 1)


# 1. normalise and stretch each line separately; OIII is much fainter, so it gets a much stronger stretch
H = stretch(norm(load(a.ha), a.lo), a.ha_mid)
O = stretch(norm(load(a.oiii), a.lo, 99.9), min(0.45, a.ha_mid * a.o_boost))

# 2. brightness from both lines
lum = np.clip(mtf(np.clip(a.lw * H + (1 - a.lw) * O, 0, 1), a.lum_m), 0, 1)

# 3. hue from the OIII share, rescaled to the range actually present in the nebula
t = O / np.maximum(H + O, 1e-6)
neb = lum > np.percentile(lum, 60)
lo, hi = np.percentile(t[neb], a.t_lo), np.percentile(t[neb], a.t_hi)
t = gaussian_filter(np.clip((t - lo) / (hi - lo), 0, 1), 1.5)
t = t * t * (3 - 2 * t)  # smooth transition gold -> blue
col = np.array(a.gold) * (1 - t[..., None]) + np.array(a.blue) * t[..., None]
rgb = lum[..., None] * col / np.maximum(col.mean(-1, keepdims=True) / 0.62, 1e-6)

# 4. faint areas fade to neutral grey, so the background is not blotchy blue
w = np.clip(lum / a.neutral_lo, 0, 1)[..., None]
w = w * w * (3 - 2 * w)
g = rgb.mean(-1, keepdims=True)
rgb = np.clip(g + (rgb - g) * w, 0, 1)

# 5. large-scale local contrast (darker cavity, clearer ring) and saturation
L = rgb.mean(-1)
L2 = np.clip(L + a.lc * (L - gaussian_filter(L, 60)), 0, 1)
rgb = rgb * (L2 / np.maximum(L, 1e-6))[..., None]
g = rgb.mean(-1, keepdims=True)
rgb = np.clip(g + a.sat * (rgb - g), 0, 1)

# share of pixels sitting at the black point BEFORE the pedestal: this is the real shadow loss
floor_pct = float((rgb.max(-1) < 1 / 255).mean() * 100)

# 6. neutral pedestal: background becomes dark grey instead of pure black.
#    It only lifts the floor, it does NOT recover shadow detail lost at the black point.
rgb = a.ped + rgb * (1 - a.ped)

# 7. stars back with muted colour, screen blend
if a.stars:
    s = load(a.stars)
    s = np.moveaxis(s, 0, -1) if s.shape[0] == 3 else s
    s = np.clip(s / np.percentile(s, 99.97), 0, 1)
    s = np.clip(mtf(s, a.star_m), 0, 1)
    sg = s.mean(-1, keepdims=True)
    s = np.clip(sg + a.star_sat * (s - sg), 0, 1)
    rgb = 1 - (1 - rgb) * (1 - a.stars_amt * s)

rgb = np.clip(rgb, 0, 1)
tifffile.imwrite(a.out + '_16bit.tiff', (rgb * 65535).astype(np.uint16), photometric='rgb')
Image.fromarray((rgb * 255).astype(np.uint8)).save(a.out + '.jpg', quality=95)
json.dump(vars(a), open(a.out + '_params.json', 'w'), indent=1)
print(f'saved {a.out}_16bit.tiff and {a.out}.jpg, {rgb.shape[1]}x{rgb.shape[0]}')
print(f'pixels at the black point before pedestal: {floor_pct:.2f}% (lower --lo if this is high)')
