"""
Resolution Estimator (EXPERIMENTAL)

Estimates a video's internal render resolution through frequency analysis:
an image rendered internally at, say, 1440p and upscaled to 4K contains no
real detail above the 1440p Nyquist frequency. The cut-off edge in the
spectrum (measured per axis) reveals the scaling ratio.

Limits (deliberate, stated honestly):
- Temporal reconstruction (DLSS/FSR2/TAAU) synthesises real detail up to the
  output resolution, so the internal raster resolution cannot be read cleanly
  from the image at all. Such frames are flagged as
  "native/reconstruction" instead of being given a wrong number.
- Sharpening filters push the edge upwards (measurements read high), heavy
  motion blur pushes it down. Hence many samples and a temporal median.
- The HUD is rendered natively, so measurement uses a centre crop without
  the UI edges.
"""

import numpy as np
import cv2


def _axis_cutoff(gray_f32, axis, drop_db=4.0):
    """
    Spectral cut-off edge via TREND DEVIATION: fit a trend line through the
    low-frequency band (10-40% Nyquist); the cutoff is the first frequency at
    which the spectrum falls SUSTAINEDLY drop_db below that trend (upscaling
    rolloff is a gentle curve, not a step - measured against ground truth).
    No sustained drop = native. Returns (ratio, max_deviation_db).
    """
    if axis == 0:
        data = gray_f32.T
    else:
        data = gray_f32

    n = data.shape[1]
    if n < 64:
        return 1.0, 0.0

    rows = data
    if rows.shape[0] > 256:
        sel = np.linspace(0, rows.shape[0] - 1, 256).astype(np.int32)
        rows = rows[sel]

    rows = rows - rows.mean(axis=1, keepdims=True)
    win = np.hanning(n).astype(np.float32)
    spec = np.abs(np.fft.rfft(rows * win, axis=1)) ** 2
    p_db = 10.0 * np.log10(spec.mean(axis=0) + 1e-12)
    k = 5
    p_s = np.convolve(p_db, np.ones(k, dtype=np.float32) / k, mode='same')
    m = len(p_s)

    # Extrapolate the trend from the low-frequency band
    b0, b1 = int(0.10 * m), int(0.40 * m)
    xs = np.arange(m, dtype=np.float32)
    coef = np.polyfit(xs[b0:b1], p_s[b0:b1], 1)
    trend = np.polyval(coef, xs)
    resid = p_s - trend

    sustain = max(4, m // 25)
    lo = int(0.42 * m)
    hi = int(0.985 * m) - sustain
    cutoff_idx = None
    for i in range(lo, hi):
        if resid[i] < -drop_db and resid[i:i + sustain].mean() < -drop_db:
            cutoff_idx = i
            break
    max_dev = float(-resid[lo:].min()) if hi > lo else 0.0
    if cutoff_idx is None:
        return 1.0, max_dev
    ratio = min(1.0, max(0.05, cutoff_idx / max(1, m - 1)))
    return ratio, max_dev


def estimate_internal_resolution(frame_bgr, crop_frac=0.5):
    """
    Estimates the internal render resolution of a single frame.
    crop_frac: zentraler Bildanteil (0.5 = mittlere 50% je Achse) — meidet HUD.
    Returns dict: width_est, height_est, ratio_x, ratio_y, confidence, native_or_recon
    """
    h, w = frame_bgr.shape[:2]
    cw, ch = int(w * crop_frac), int(h * crop_frac)
    x0, y0 = (w - cw) // 2, (h - ch) // 2
    crop = frame_bgr[y0:y0 + ch, x0:x0 + cw]

    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY).astype(np.float32)

    # Detail metric: median row energy in the mid band (20-40% Nyquist).
    # Frames with little structure (flat areas, little texture) give no reliable
    # cutoff measurement - they are marked 'uncertain' rather than wrongly 'native'.
    _rows = gray - gray.mean(axis=1, keepdims=True)
    if _rows.shape[0] > 128:
        _sel = np.linspace(0, _rows.shape[0] - 1, 128).astype(np.int32)
        _rows = _rows[_sel]
    _n = _rows.shape[1]
    _spec = np.abs(np.fft.rfft(_rows * np.hanning(_n).astype(np.float32),
                               axis=1)) ** 2
    _m = _spec.shape[1]
    _band = _spec[:, int(0.2 * _m):int(0.4 * _m)].mean(axis=1)
    detail_db = float(10.0 * np.log10(np.median(_band) + 1e-12))

    rx, cx = _axis_cutoff(gray, axis=1)
    ry, cy = _axis_cutoff(gray, axis=0)

    width_est  = int(round(w * rx))
    height_est = int(round(h * ry))
    conf = min(cx, cy)
    native_or_recon = (rx >= 0.95 and ry >= 0.95)
    return {
        'width_est': width_est,
        'height_est': height_est,
        'ratio_x': rx,
        'ratio_y': ry,
        'confidence': conf,
        'detail_db': detail_db,
        'unreliable': detail_db < 55.0,
        'native_or_recon': native_or_recon,
    }


COMMON_HEIGHTS = [2160, 1800, 1620, 1440, 1296, 1080, 900, 720]

def _snap_height(h_est, tol=0.06):
    """Nearest common resolution height, if within tolerance."""
    for h in COMMON_HEIGHTS:
        if abs(h_est - h) / h <= tol:
            return h
    return None


def probe_video(path, samples=40, crop_frac=0.5, progress_cb=None,
                cancel_check=None):
    """
    Measures `samples` frames spread evenly across a video.
    Returns (results_list, report_str). results_list: Einzelmessungen.
    """
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        return [], f"❌ Video not readable: {path}"
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    if total < 2:
        cap.release()
        return [], "❌ Zu wenige Frames"

    idxs = np.linspace(int(total * 0.03), int(total * 0.97),
                       min(samples, total)).astype(np.int64)
    results = []
    for i, fi in enumerate(idxs):
        if cancel_check and cancel_check():
            break
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(fi))
        ret, frame = cap.read()
        if not ret:
            continue
        r = estimate_internal_resolution(frame, crop_frac=crop_frac)
        r['frame'] = int(fi)
        results.append(r)
        if progress_cb:
            progress_cb(i + 1, len(idxs))
    cap.release()

    if not results:
        return [], "❌ No measurements possible"

    reliable = [r for r in results if not r.get('unreliable')]
    base = reliable if reliable else results
    hs = np.array([r['height_est'] for r in base], dtype=np.float32)
    ws = np.array([r['width_est'] for r in base], dtype=np.float32)
    confs = np.array([r['confidence'] for r in base], dtype=np.float32)
    n_native = sum(1 for r in base if r['native_or_recon'])
    n_unrel = len(results) - len(reliable)

    med_h, med_w = float(np.median(hs)), float(np.median(ws))
    mad_h = float(np.median(np.abs(hs - med_h)))
    snap = _snap_height(med_h)

    lines = []
    lines.append(f"📐 RESOLUTION ANALYSIS (experimental) - {path}")
    lines.append(f"   Container: {w}x{h}, {len(results)} Messframes"
                 + (f" ({n_unrel} davon wenig Bilddetail → ausgeschlossen)"
                    if n_unrel else ""))
    if not reliable:
        lines.append("   ⚠️ ALL frames lack structure - measurement NOT reliable!")
    lines.append(f"   Median internal: ~{med_w:.0f} x {med_h:.0f}"
                 + (f"  -> nearest common: {snap}p" if snap else ""))
    lines.append(f"   Spread (MAD height): +/-{mad_h:.0f}px | "
                 f"Signal quality: {float(np.median(confs)):.0f}dB")
    lines.append(f"   Min/Max height: {hs.min():.0f} / {hs.max():.0f}")
    if n_native > len(base) * 0.6:
        lines.append("   ⚠️ Most frames measure ~native - either real native "
                     "rendering OR temporal reconstruction (DLSS/FSR2/"
                     "TAAU); the latter cannot be told apart from the image.")
    if mad_h > med_h * 0.08:
        lines.append("   ℹ️ High spread -> suggests dynamic resolution (DRS)")
    lines.append("   Individual values (frame -> width x height):")
    for r in results:
        tag = " [native/recon]" if r['native_or_recon'] else ""
        if r.get('unreliable'):
            tag += " [wenig Detail — unsicher]"
        lines.append(f"     {r['frame']:6d} → {r['width_est']:4d} x "
                     f"{r['height_est']:4d}{tag}")
    return results, "\n".join(lines)
