# Blue and gold from duo-band data: my DWARF Mini workflow, step by step

How I got the Hubble-style Rosette ([AstroBin](https://app.astrobin.com/i/u0bd2k), revision D) from a 30 mm smart telescope on a city balcony. Every number below is the setting actually used on this image. The linear stack is [here](https://github.com/tepliyk/astro-data/releases/tag/data-ngc2244-rosette) if you want to follow along with the same data.

![From raw stack to final](img/07_final.jpg)

**Data:** DWARF Mini, Alt-Az, built-in duo-band filter, gain 80, 2-panel mosaic, 1415 x 60 s over 10 nights (23.6 h).

## What you need

| Step | What I used | Free alternative |
|---|---|---|
| Stacking | [Siril 1.4](https://siril.org) | same |
| Gradient removal | [GraXpert](https://graxpert.com) | same, or Siril Background Extraction |
| Deconvolution (optional) | BlurXTerminator | skip it, or Siril deconvolution |
| Star removal | StarXTerminator | StarNet (built into Siril) |
| Noise reduction | NoiseXTerminator | GraXpert denoising, Siril denoise |
| Colour mapping | [hubble_map.py](../scripts/hubble_map.py) (Python) | Siril PixelMath, see step 9 |

Python: `pip install numpy scipy astropy tifffile pillow`

## 1. Collect the raw subs, not the in-app stacks

The Mini keeps every sub as FITS in `Astronomy/DWARF_RAW_TELE_<target>_<date>/`. A mosaic has one subfolder per panel. Copy the subs of one target (or one panel) from **all nights** into a single `lights/` folder.

Why not combine the nightly in-app stacks? Inside a finished stack you can no longer reject bad frames. Restacking all subs together let me drop cloudy and trailed frames across all nights and weight the rest by quality. On another target this gave about 20% better signal-to-noise than combining nightly stacks.

## 2. Calibration frames

In the `CALI_FRAME` folder of the Mini:

- **Darks:** `dark/cam_0/dark_exp_60.000000_gain_80_*` with the same exposure and gain as your lights. I took the ones recorded at 18 to 26 °C, the range of my nights, and stacked them into a master dark in Siril (`stack dark rej 3 3 -nonorm`).
- **Flat and bias:** `flat/cam_0/flat_gain_2_bin_1_ir_2.fits` and `bias/cam_0/bias_gain_2_bin_1.fits`, used as they are.

## 3. Stack in Siril

The script [siril_dwarf_panel.ssf](../scripts/siril_dwarf_panel.ssf) does everything in one run. The key lines:

```
calibrate light -dark=../master_dark -flat=../master_flat -bias=../master_bias -cfa -equalize_cfa -debayer
register pp_light -2pass
seqapplyreg pp_light -filter-wfwhm=90% -filter-round=90% -filter-bkg=90%
stack r_pp_light rej w 3 3 -norm=addscale -output_norm -rgb_equal -filter-included -weight=wfwhm -out=../stack
```

- `-cfa -equalize_cfa -debayer`: the Mini is a colour camera, debayer after calibration.
- `-filter-...=90%`: keep the best 90% by star sharpness (FWHM), roundness (tracking) and background (clouds, light pollution). This is what removes the bad frames from all nights at once.
- `rej w 3 3`: winsorized sigma clipping, removes satellites and hot pixels.
- `-weight=wfwhm`: sharper frames count more.

Result here: 731 subs in panel 1 and 684 in panel 2.

![Linear stack, auto-stretched](img/02_linear_autostretch_unlinked.jpg)

*The stack with a quick auto-stretch. Green and purple gradients are light pollution, they go in step 5.*

## 4. Mosaic (skip if you shot one panel)

Siril can build the mosaic itself: `seqplatesolve`, then `register -astrometric`, then `stack ... -overlap_norm`. Plate solving needs a star catalogue. The online one was down for me, so install the local Gaia catalogue in Siril (Catalog_Installer script) and it works offline.

I ended up joining the two panels in Python with `astroalign` (star-based alignment) and a 120 px feathered seam, then cropped the empty borders. Either way the result is one linear RGB image.

## 5. Gradient, deconvolution, star removal

On the linear RGB image:

1. **Gradient removal.** Remove the light pollution gradient. I fitted a 2nd-order polynomial to the frame edges, where there is no nebula. GraXpert or Siril Background Extraction do the same job.
2. **Deconvolution (optional).** BlurXTerminator with stars 0.25 and non-stellar 0.60. Mostly tightens the bloated stars at 150 mm.
3. **Star removal.** StarXTerminator with "stars" output, so you get two files: a starless image and a stars-only image. Keep both, the stars go back at the end.

![Starless](img/03_starless.jpg)

*Starless, still in natural colour.*

## 6. Split Ha and OIII

With a duo-band filter on a colour camera, Ha (656 nm) lands on the red pixels and OIII (501 nm) on the green and blue ones. So:

- **Ha = R**
- **OIII = (G + B) / 2**

```
python split_ho.py starless.fits .
```

[split_ho.py](../scripts/split_ho.py) writes `Ha.fits` and `OIII.fits`. In Siril the same is Extraction → Split channels, then PixelMath `(G+B)/2`.

## 7. Clean each channel separately

From here Ha and OIII are two separate mono images, and they need different treatment because OIII is several times weaker.

1. **GraXpert background extraction** on each: correction Subtraction, smoothing 0.5. Gradients left over in one channel become colour blotches later.
2. **Noise reduction, stronger on OIII:** NoiseXTerminator 0.75 on Ha, 0.95 with 3 iterations on OIII.

| Ha | OIII |
|---|---|
| ![Ha](img/04_ha.jpg) | ![OIII](img/05_oiii.jpg) |

*Both after cleaning and stretching. They look similar, but the ratio between them is what drives the colour.*

## 8. Stretch Ha and OIII separately

This is the main trick for blue and gold. If you stretch both channels the same way, OIII stays dim and the gold swallows the blue.

Each channel is stretched so that its 75th percentile (the faint nebula level) lands at a chosen brightness:

- Ha to **0.30**
- OIII to **0.255**

Since OIII starts much weaker, reaching almost the same level means a much harder stretch. Black point at the 2nd percentile, **not** the median: a median black point clips half the background to zero (that was my mistake in the first version, see step 11).

## 9. Map the colour

The easy way is a linear mix, and it works in Siril PixelMath (three expressions, RGB output):

```
R = Ha + 0.36 * OIII
G = 0.60 * Ha + 0.66 * OIII
B = 0.22 * Ha + OIII
```

The catch: where both lines are strong, all three channels go high and the core turns white. The classic Foraxx formula did the same on this data.

What [hubble_map.py](../scripts/hubble_map.py) does instead:

1. **Brightness** from both lines: `L = 0.55 * Ha + 0.45 * OIII`.
2. **Hue** from the OIII share in each pixel: `t = OIII / (Ha + OIII)`.
3. `t` is rescaled to the range actually present in the nebula (14th to 94th percentile), so the full gold-to-blue range is used, then smoothed.
4. Colour = gold `(1.0, 0.60, 0.22)` blended to blue `(0.36, 0.66, 1.0)` by `t`, multiplied by `L`.

Since brightness and hue are separate, the core can be bright and still blue.

![Hue map](img/06_hue_map.jpg)

*Gold where hydrogen dominates, blue where oxygen does. Oxygen sits close to the hot young stars of NGC 2244, hydrogen further out.*

## 10. Finish

Also in the script, all optional:

- **Neutral background:** below brightness 0.12 the colour fades to grey, so noise in the background does not turn into blue and gold blotches.
- **Local contrast:** 0.35 on a 60 px scale. Darkens the central cavity, brings out the ring.
- **Saturation:** 1.12.
- **Pedestal:** the whole image is lifted by 0.06, so the background is dark grey instead of pure black.

## 11. Stars back, and check the blacks

- The stars-only image is stretched separately (midtone 0.03), its colour reduced to 45%, and added back with a screen blend at 0.8. Muted stars do not compete with the nebula and avoid pink halos.
- **Check the histogram.** My first version had 38% of the pixels at 0 to 2 out of 255, a commenter spotted the clipped background. With the black point at the 2nd percentile and the pedestal, it is 0% now. The script prints this number at the end.

```
python hubble_map.py --ha Ha.fits --oiii OIII.fits --stars stars.fits --out rosette
```

All the numbers above are the script defaults. Add `--flip` if your image comes out upside down (some tools write FITS bottom-up).

## Summary

1. Restack all raw subs from all nights in Siril, with filtering by FWHM, roundness and background.
2. Remove gradients and stars while still linear.
3. Split into Ha = R and OIII = (G+B)/2, clean each separately, more noise reduction on OIII.
4. Stretch them separately, OIII much harder.
5. Brightness from both lines, hue from the OIII share.
6. Neutral background, stars back muted, check that nothing is clipped.

Questions are welcome on Reddit (u/Different_Crew_8867) or in my Telegram channel [Nebo Blyzhche](https://t.me/nebo_blyzhche). Night-by-night log for this target: [tepliyk.github.io/en/ngc-2244](https://tepliyk.github.io/en/ngc-2244/).
