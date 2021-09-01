#!/usr/bin/env python
"""
Created on May 23, 2013
@author: Cheng Chang (cheng.chang.ece@gmail.com)
         Computer Science Group, Computational Science Center
         Brookhaven National Laboratory

This code is for Differential Phase Contrast (DPC) imaging based on Fourier-shift fitting
implementation.

Reference: Yan, H. et al. Quantitative x-ray phase imaging at the nanoscale by multilayer
           Laue lenses. Sci. Rep. 3, 1307; DOI:10.1038/srep01307 (2013).

Test data is available at:
https://docs.google.com/file/d/0B3v6W1bQwN_AdjZwWmE3WTNqVnc/edit?usp=sharing
"""
from __future__ import print_function, division
import os
import numpy as np
import matplotlib.pyplot as plt
import PIL

from scipy.optimize import minimize
import time
from six import StringIO
import dpcmaps.load_timepix as load_timepix
import h5py

from dpcmaps.db_config.db_config import db

# try:
#     import filestore.api as fsapi
# except Exception:
#     print("Filestore is not available.")


rss_cache = {}
rss_iters = 0


def get_beta(xdata):
    length = len(xdata)
    try:
        beta = rss_cache[length]
    except Exception:
        # beta = 1j * (np.arange(length) + 1 - (np.floor(length / 2.0) + 1))
        beta = 1j * (np.arange(length) - np.floor(length / 2.0))
        rss_cache[length] = beta

    return beta


def rss(v, xdata, ydata, beta):
    """Function to be minimized in the Nelder Mead algorithm"""
    fitted_curve = xdata * v[0] * np.exp(v[1] * beta)
    return np.sum(np.abs(ydata - fitted_curve) ** 2)


def pil_load(fn):
    im = PIL.Image.open(fn)

    def toarray(im, dtype=np.uint8):
        x_str = im.tostring("raw", im.mode)
        return np.fromstring(x_str, dtype)

    assert im.mode.startswith("I;16")
    if im.mode.endswith("B"):
        x = toarray(im, ">u2")
    else:
        x = toarray(im, "<u2")

    x.shape = im.size[1], im.size[0]
    return x.astype("=u2")


def load_image_filestore(datum_id):
    if datum_id is None:
        raise IOError("Image doesn't exist yet")

    # raise Exception(f"Reading image: datum_id = {datum_id}")

    try:
        return np.asarray(db.reg.retrieve(datum_id)).squeeze()
        # return np.asarray(fsapi.retrieve(datum_id)).squeeze()
    except Exception as ex:
        print("Filestore load failed (datum={}): ({}) {}" "".format(datum_id, ex.__class__.__name__, ex))
        raise


def load_data_hdf5(file_path):
    """
    Read images using the h5py lib
    """
    f = h5py.File(str(file_path), "r")
    entry = f["entry"]
    instrument = entry["instrument"]
    detector = instrument["detector"]
    dsdata = detector["data"]
    data = dsdata[...]
    f.close()

    return np.array(data)


def load_file(load_image, fn, hang, roi=None, bad_pixels=[], zip_file=None):
    """
    Load an image file
    """
    if load_image == load_image_filestore:
        # ignore hanging settings, just hit filestore
        try:
            im = load_image(fn)
        except Exception:
            return None, None, None
    else:
        if hang == 1:
            while not os.path.exists(fn):
                time.sleep(0.1)
            else:
                im = load_image(fn)

        elif os.path.exists(fn):
            im = load_image(fn)

        elif zip_file is not None:
            raise NotImplementedError

            # loading from a zip file is just about as fast (when not running in
            # parallel)
            f = zip_file.open(fn)
            stream = StringIO.StringIO()
            stream.write(f.read())
            f.close()

            stream.seek(0)
            im = plt.imread(stream, format="tif")
        else:
            raise Exception("File not found: %s" % fn)

    if bad_pixels is not None:
        for x, y in bad_pixels:
            im[y, x] = 0

    if roi is not None:
        x1, y1, x2, y2 = roi
        im = im[y1 : y2 + 1, x1 : x2 + 1]

    xline = np.sum(im, axis=0)
    yline = np.sum(im, axis=1)

    fx = np.fft.fftshift(np.fft.ifft(xline))
    fy = np.fft.fftshift(np.fft.ifft(yline))

    return im, fx, fy


def load_file_h5(im, roi=None, bad_pixels=[]):

    if bad_pixels is not None:
        for x, y in bad_pixels:
            im[y, x] = 0

    if roi is not None:
        x1, y1, x2, y2 = roi
        im = im[y1 : y2 + 1, x1 : x2 + 1]

    xline = np.sum(im, axis=0)
    yline = np.sum(im, axis=1)

    fx = np.fft.fftshift(np.fft.ifft(xline))
    fy = np.fft.fftshift(np.fft.ifft(yline))

    return im, fx, fy


def xj_test(filename, i, j, hang, roi=None, bad_pixels=[], **kwargs):
    try:
        im, fx, fy = load_file(filename, zip_file=zip_file, hang=hang, roi=roi, bad_pixels=bad_pixels)
    except Exception:
        # print('Failed to load file %s: %s' % (filename, ex))
        return 0.0, 0.0, 0.0

    wx, wy = im.shape
    gx = np.sum(im[: wx // 2, :]) - np.sum(im[wx // 2 :, :])
    gy = np.sum(im[:, : wy // 2]) - np.sum(im[:, wy // 2 :])
    return 0, gx, gy


def run_dpc(
    filename,
    i,
    j,
    ref_fx=None,
    ref_fy=None,
    start_point=[1, 0],
    pixel_size=55,
    focus_to_det=1.46,
    dx=0.1,
    dy=0.1,
    energy=19.5,
    zip_file=None,
    roi=None,
    bad_pixels=[],
    max_iters=1000,
    solver="Nelder-Mead",
    hang=True,
    reverse_x=1,
    reverse_y=1,
    load_image=load_timepix.load,
):
    """
    All units in micron

    pixel_size
    focus_to_det: focus to detector distance
    dx: scan step size x
    dy: scan step size y
    energy: in keV
    """
    try:
        img, fx, fy = load_file(load_image, filename, hang=hang, zip_file=zip_file, roi=roi, bad_pixels=bad_pixels)
    except IOError as ie:
        print("%s" % ie)
        return 0.0, 0.0, 0.0, 0.0, 0.0

    if img is None:
        print("Image {0} was not loaded.".format(filename))
        return 1e-5, 1e-5, 1e-5, 1e-5, 1e-5

    # vx = fmin(rss, start_point, args=(ref_fx, fx, get_beta(ref_fx)),
    #           maxiter=max_iters, maxfun=max_iters, disp=0)
    res = minimize(
        rss,
        start_point,
        args=(ref_fx, fx, get_beta(ref_fx)),
        method=solver,
        tol=1e-6,
        options=dict(maxiter=max_iters),
    )

    vx = res.x
    rx = res.fun
    a = vx[0]
    gx = reverse_x * vx[1]

    # vy = fmin(rss, start_point, args=(ref_fy, fy, get_beta(ref_fy)),
    #          maxiter=max_iters, maxfun=max_iters, disp=0)
    res = minimize(
        rss,
        start_point,
        args=(ref_fy, fy, get_beta(ref_fy)),
        method=solver,
        tol=1e-6,
        options=dict(maxiter=max_iters),
    )

    vy = res.x
    ry = res.fun
    gy = reverse_y * vy[1]

    # print(i, j, vx[0], vx[1], vy[1])
    return a, gx, gy, rx, ry


def run_dpc_h5(
    dataimg,
    i,
    j,
    ref_fx=None,
    ref_fy=None,
    start_point=[1, 0],
    pixel_size=55,
    focus_to_det=1.46,
    dx=0.1,
    dy=0.1,
    energy=19.5,
    zip_file=None,
    roi=None,
    bad_pixels=[],
    max_iters=1000,
    solver="Nelder-Mead",
    hang=True,
    reverse_x=1,
    reverse_y=1,
    load_image=None,
):
    """
    All units in micron

    pixel_size
    focus_to_det: focus to detector distance
    dx: scan step size x
    dy: scan step size y
    energy: in keV
    """
    try:
        img, fx, fy = load_file_h5(dataimg, roi=roi, bad_pixels=bad_pixels)
    except IOError as ie:
        print("%s" % ie)
        return 0.0, 0.0, 0.0, 0.0, 0.0

    if img is None:
        return 1e-5, 1e-5, 1e-5, 1e-5, 1e-5

    # vx = fmin(rss, start_point, args=(ref_fx, fx, get_beta(ref_fx)),
    #           maxiter=max_iters, maxfun=max_iters, disp=0)
    res = minimize(
        rss,
        start_point,
        args=(ref_fx, fx, get_beta(ref_fx)),
        method=solver,
        tol=1e-6,
        options=dict(maxiter=max_iters),
    )

    vx = res.x
    rx = res.fun
    a = vx[0]
    gx = reverse_x * vx[1]

    # vy = fmin(rss, start_point, args=(ref_fy, fy, get_beta(ref_fy)),
    #          maxiter=max_iters, maxfun=max_iters, disp=0)
    res = minimize(
        rss,
        start_point,
        args=(ref_fy, fy, get_beta(ref_fy)),
        method=solver,
        tol=1e-6,
        options=dict(maxiter=max_iters),
    )

    vy = res.x
    ry = res.fun
    gy = reverse_y * vy[1]

    # print(i, j, vx[0], vx[1], vy[1])
    return a, gx, gy, rx, ry


def recon(gx, gy, dx=0.1, dy=0.1, pad=1, w=1.0):
    """
    Reconstruct the final phase image
    Parameters
    ----------
    gx : 2-D numpy array
        phase gradient along x direction

    gy : 2-D numpy array
        phase gradient along y direction

    dx : float
        scanning step size in x direction (in micro-meter)

    dy : float
        scanning step size in y direction (in micro-meter)

    pad : float
        padding parameter
        default value, pad = 1 --> no padding
                    p p p
        pad = 3 --> p v p
                    p p p

    w : float
        weighting parameter for the phase gradient along x and y direction when
        constructing the final phase image

    Returns
    ----------
    phi : 2-D numpy array
        final phase image

    References
    ----------
    [1] Yan, Hanfei, Yong S. Chu, Jorg Maser, Evgeny Nazaretski, Jungdae Kim,
    Hyon Chol Kang, Jeffrey J. Lombardo, and Wilson KS Chiu, "Quantitative
    x-ray phase imaging at the nanoscale by multilayer Laue lenses," Scientific
    reports 3 (2013).

    """

    rows, cols = gx.shape

    gx_padding = np.zeros((pad * rows, pad * cols), dtype="d")
    gy_padding = np.zeros((pad * rows, pad * cols), dtype="d")

    gx_padding[(pad // 2) * rows : (pad // 2 + 1) * rows, (pad // 2) * cols : (pad // 2 + 1) * cols] = gx
    gy_padding[(pad // 2) * rows : (pad // 2 + 1) * rows, (pad // 2) * cols : (pad // 2 + 1) * cols] = gy

    tx = np.fft.fftshift(np.fft.fft2(gx_padding))
    ty = np.fft.fftshift(np.fft.fft2(gy_padding))

    c = np.zeros((pad * rows, pad * cols), dtype=complex)

    mid_col = pad * cols // 2 + 1
    mid_row = pad * rows // 2 + 1

    ax = 2 * np.pi * (np.arange(pad * cols) + 1 - mid_col) / (pad * cols * dx)
    ay = 2 * np.pi * (np.arange(pad * rows) + 1 - mid_row) / (pad * rows * dy)

    kappax, kappay = np.meshgrid(ax, ay)

    c = -1j * (kappax * tx + w * kappay * ty)

    c = np.ma.masked_values(c, 0)
    c /= kappax ** 2 + w * kappay ** 2
    c = np.ma.filled(c, 0)

    c = np.fft.ifftshift(c)
    phi_padding = np.fft.ifft2(c)
    phi_padding = -phi_padding.real

    phi = phi_padding[(pad // 2) * rows : (pad // 2 + 1) * rows, (pad // 2) * cols : (pad // 2 + 1) * cols]

    return phi


def main(
    file_format="SOFC/SOFC_%05d.tif",
    dx=0.1,
    dy=0.1,
    ref_image=None,
    zip_file=None,
    rows=121,
    cols=121,
    start_point=[1, 0],
    pixel_size=55,
    focus_to_det=1.46,
    energy=19.5,
    pool=None,
    first_image=1,
    x1=None,
    x2=None,
    y1=None,
    y2=None,
    bad_pixels=[],
    solver="Nelder-Mead",
    display_fcn=None,
    random=1,
    pyramid=-1,
    hang=1,
    swap=-1,
    reverse_x=1,
    reverse_y=1,
    mosaic_x=121,
    mosaic_y=121,
    load_image=load_timepix.load,
    use_mds=False,
    use_hdf5=False,
    scan=None,
    save_path=None,
    pad=False,
    calculate_results=False,
):
    print("DPC")
    print("---")
    print("\tFile format: %s" % file_format)
    print("\tdx: %s" % dx)
    print("\tdy: %s" % dy)
    print("\trows: %s" % rows)
    print("\tcols: %s" % cols)
    print("\tstart point: %s" % start_point)
    print("\tpixel size: %s" % pixel_size)
    print("\tfocus to det: %s" % (focus_to_det))
    print("\tenergy: %s" % energy)
    print("\tfirst image: %s" % first_image)
    print("\treference image: %s" % ref_image)
    print("\tsolver: %s" % solver)
    print("\thang : %s" % hang)
    print("\tswap : %s" % swap)
    print("\treverse_x : %s" % reverse_x)
    print("\treverse_y : %s" % reverse_y)
    print("\tROI: (%s, %s)-(%s, %s)" % (x1, y1, x2, y2))
    print("\tUse mds : %s" % use_mds)
    print("\tUse hdf5 : %s" % use_hdf5)
    print("\tScan : %s" % scan)

    if display_fcn is not None:
        calculate_results = True

    t0 = time.time()

    roi = None
    if x1 is not None and x2 is not None:
        if y1 is not None and y2 is not None:
            roi = (x1, y1, x2, y2)

    if use_hdf5:
        # load the data
        datastack = load_data_hdf5(file_format)

        # read the reference image hdf5: only one reference image
        reference, ref_fx, ref_fy = load_file_h5(datastack[first_image - 1, :, :], roi=roi, bad_pixels=bad_pixels)

    else:
        # read the reference image: only one reference image
        reference, ref_fx, ref_fy = load_file(
            load_image, ref_image, hang, zip_file=zip_file, roi=roi, bad_pixels=bad_pixels
        )

    a = np.zeros((rows, cols), dtype="d")
    gx = np.zeros((rows, cols), dtype="d")
    gy = np.zeros((rows, cols), dtype="d")
    rx = np.zeros((rows, cols), dtype="d")
    ry = np.zeros((rows, cols), dtype="d")

    dpc_settings = dict(
        start_point=start_point,
        pixel_size=pixel_size,
        focus_to_det=focus_to_det,
        dx=dx,
        dy=dy,
        energy=energy,
        zip_file=zip_file,
        ref_fx=ref_fx,
        ref_fy=ref_fy,
        roi=roi,
        bad_pixels=bad_pixels,
        solver=solver,
        load_image=load_image,
        hang=hang,
        reverse_x=reverse_x,
        reverse_y=reverse_y,
    )

    if use_mds:
        image_uids = list(scan)
        print("Filestore has %d images" % (len(image_uids)))

        def get_filename(i, j):
            idx = first_image + i * cols + j
            try:
                return image_uids[idx]
            except IndexError:
                return None

    elif use_hdf5:

        def get_filename(i, j):
            frame_num = first_image + i * cols + j - 1
            return frame_num

    else:

        def get_filename(i, j):
            frame_num = first_image + i * cols + j
            return file_format % frame_num

    # Wavelength in micron
    lambda_ = 12.4e-4 / energy

    _t0 = time.time()

    mrows = rows // mosaic_y
    mcols = cols // mosaic_x

    if 1:
        fcn = run_dpc
    else:
        fcn = xj_test

    gx_factor = len(ref_fx) * pixel_size / (lambda_ * focus_to_det * 1e6)
    gy_factor = len(ref_fy) * pixel_size / (lambda_ * focus_to_det * 1e6)

    for n in range(mosaic_y):
        for m in range(mosaic_x):
            if use_hdf5:
                args = [
                    (datastack[get_filename(i, j), :, :], i, j)
                    for i in range(n * mrows, n * mrows + mrows)
                    for j in range(m * mcols, m * mcols + mcols)
                ]
            else:
                args = [
                    (get_filename(i, j), i, j)
                    for i in range(n * mrows, n * mrows + mrows)
                    for j in range(m * mcols, m * mcols + mcols)
                ]

            try:

                if display_fcn is not None and random == 1:
                    np.random.shuffle(args)

                # Function call without multiprocessing for debugging
                #                 for arg in args:
                #                     results = fcn(arg[0],arg[1],arg[2], ref_fx=ref_fx, roi=roi)

                if use_hdf5:
                    fcn = run_dpc_h5

                results = [pool.apply_async(fcn, arg, kwds=dpc_settings) for arg in args]

                if calculate_results:
                    total_results = len(results)
                    k = 0
                    while k < total_results:
                        k = 0
                        for arg, result in zip(args, results):
                            if result.ready():
                                _a, _gx, _gy, _rx, _ry = result.get()
                                fn, i, j = arg

                                if pyramid == 1 and i % 2 != 0:
                                    j = mcols - j - 1

                                a[i, j] = _a
                                rx[i, j] = _rx
                                ry[i, j] = _ry
                                if swap == 1:
                                    gy[i, j] = _gx * gx_factor
                                    gx[i, j] = _gy * gy_factor
                                else:
                                    gx[i, j] = _gx * gx_factor
                                    gy[i, j] = _gy * gy_factor
                                k += 1

                        try:
                            if display_fcn is not None:
                                display_fcn(a, gx, gy, None, rx, ry)
                        except Exception as ex:
                            print("Failed to update display: (%s) %s" % (ex.__class__.__name__, ex))

                        time.sleep(1.0)
            except KeyboardInterrupt:
                print("Cancelled")
                return
    pool.close()
    pool.join()

    _t1 = time.time()
    elapsed = _t1 - _t0
    print(
        "Multiprocess elapsed=%.3f frames=%d (per frame %.3fms)"
        "" % (elapsed, rows * cols, 1000 * elapsed / (rows * cols))
    )

    dim = len(np.squeeze(gx).shape)
    if dim != 1:
        if pad is True:
            phi = recon(gx, gy, dx, dy, 3)
            print("Padding mode enabled!")
        else:
            phi = recon(gx, gy, dx, dy)
            print("Padding mode disabled!")
        t1 = time.time()
        print("Elapsed", t1 - t0)

        if display_fcn is not None:
            display_fcn(a, gx, gy, phi, rx, ry)
        return a, gx, gy, phi, rx, ry

    else:
        t1 = time.time()
        print("Elapsed", t1 - t0)

        phi = None
        if display_fcn is not None:
            display_fcn(a, gx, gy, phi, rx, ry)
        return a, gx, gy, phi, rx, ry


if __name__ == "__main__":
    zip_file = None  # zipfile.ZipFile('SOFC.zip')
    main(zip_file=zip_file, rows=121, cols=121)
