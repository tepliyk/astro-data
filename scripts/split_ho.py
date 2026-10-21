"""Split a duo-band OSC image (RGB FITS) into Ha and OIII mono FITS.

Ha (656 nm) lands on the red pixels of the Bayer matrix, OIII (501 nm) on green and blue.
So: Ha = R, OIII = (G + B) / 2. Header is kept.

    python split_ho.py starless.fits out_dir      ->  out_dir/Ha.fits, out_dir/OIII.fits

Requirements: pip install numpy astropy
"""
import os
import sys

import numpy as np
from astropy.io import fits

src, out = sys.argv[1], sys.argv[2]
with fits.open(src) as h:
    d = h[0].data.astype(np.float32)
    hd = h[0].header.copy()
if d.shape[0] != 3:          # (H, W, 3) -> (3, H, W)
    d = np.moveaxis(d, -1, 0)
hd.remove('NAXIS3', ignore_missing=True)
hd['NAXIS'] = 2
for name, arr in (('Ha', d[0]), ('OIII', 0.5 * (d[1] + d[2]))):
    fits.PrimaryHDU(arr.astype(np.float32), header=hd).writeto(os.path.join(out, name + '.fits'), overwrite=True)
    print(name, 'percentiles 1/50/99:', np.percentile(arr, [1, 50, 99]).round(5))
