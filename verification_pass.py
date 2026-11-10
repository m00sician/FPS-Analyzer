"""
Verification Pass - the "half pass" that follows the pre-pass.

PURPOSE
For speed, the pre-pass decodes at 128x128 with `flags=neighbor` (point
sampling). Out of 1080p or 4K that leaves a fraction of the pixels. In very
calm scenes (drifting clouds, a slow camera pan) the real motion then falls
below the detector threshold, and the result is sections falsely reported as
0 fps.

This pass re-checks ONLY the suspicious sections (fps~0, >=1s) and corrects
them. Everything else is left untouched.


WHY NOT SIMPLY "HIGHER RESOLUTION + LOWER THRESHOLD"
Measured: the absolute size of the diff depends heavily on the downscale
filter (AREA averages noise away and yields values ~4x smaller than NEAREST).
An absolute threshold is therefore fragile in principle, at any resolution.
So this pass decides on RELATIVE criteria.


THE THREE SIGNALS (all measured at 256px AREA on real h264 test footage)

  Region                      std     medK1      medK30    frac(K1~0)
  busy 60fps                29.52   0.0068918  0.0452575     0.00
  calm clouds REAL 60fps     6.88   0.0000730  0.0022819     0.07
  frozen, SHOULD be 0 fps    6.88   0.0000016  0.0000847     0.85
  black, SHOULD be 0 fps     0.00   0.0000000  0.0000000     1.00

  K1  = diff to the immediate neighbour frame
  K30 = diff across a 30 frame gap (half a second)

  1) frac(K1~0) - the share of practically bit-identical neighbour pairs.
     This is the SHARPEST signal: 0.07 (real motion) vs 0.85 (frozen).
     Reason: h264/HEVC encodes a genuinely repeated frame as skip blocks, so
     it decodes bit-identically. Subtle real motion never does.

  2) Growth across the time baseline (K30/K1) - the fallback for the case
     where duplicates are NOT bit-identical (e.g. noise before the encode,
     analogue capture). A frozen image stays equally similar across 30 frames
     as across 1; real motion accumulates.
     CAUTION: useless when K1~0 (division by ~0 makes the ratio explode), so
     signal 1 runs first.

  3) std - single-colour frames (fade, black screen, loading screen) are
     genuine 0 fps stretches and are confirmed immediately.


PER BLOCK, NOT PER SECTION
A suspicious section can contain a scene boundary (e.g. frozen -> black
screen). A growth test across the whole section then measures the scene
change instead of the motion and produces a massive false positive (measured:
a ratio of 285237x on a section that was in fact frozen). So every section is
split into ~1s blocks and each block is decided on its own.

Afterwards fps_seq/ft_seq are recomputed COMPLETELY from the corrected
dup_flags - not just within the section, because the rolling 1s window
reaches up to a second past the section boundary.


LIMIT - WHEN THIS PASS CANNOT DETERMINE THE RATE
Measured on real h264 test footage: in VERY calm, low-detail scenes the
encoder can destroy the duplicate signal entirely. Example: real 30fps
footage (every frame doubled) in a cloud scene -

    Working resolution   medK1 duplicate pairs   medK1 real pairs   Separation
    128                       0.00008318           0.00009143         1.10x
    256                       0.00008066           0.00008982         1.11x
    512                       0.00008553           0.00009203         1.08x
    1080                      0.00008520           0.00009221         1.08x

The encoder's quantisation spread (~8e-5) is larger than the difference
between a duplicate and a real frame. A higher resolution does NOT help
(tested up to 1080px), and neither does phase correlation (0.01px measured
against 0.1px of real drift). The information is no longer in the encode.

Consequence: this pass answers "is this really 0 fps?" RELIABLY (yes/no), but
not always "what exactly is the rate?". Such blocks are recognised via the
encoder noise floor (calibrated from blocks of the same video that are known
to be frozen) and marked as uncertain - visible in the log and in the report
under 'uncertain'. `uncertain_action` selects whether they are corrected
('correct', the default) or left at 0 fps ('keep').
"""

import subprocess
import numpy as np


# ── Tunables ─────────────────────────────────────────────────────────────────

WORK_SIZE = 256           # working resolution (pre-pass: 128 NEAREST)
MIN_SECONDS = 1.0         # ignore shorter 0 fps stretches (real drops)
FPS_SUSPECT = 1.0         # fps <= this value counts as "0 fps"
UNIFORM_STD = 3.0         # frame std below this = single colour -> really 0 fps
NEAR_ZERO_MAD = 2e-5      # K1 below this = practically bit-identical (duplicate)
DUP_FRAC_CONFIRM = 0.50   # from this share of bit-identical pairs: 0 fps confirmed
GROWTH_RATIO_MIN = 3.0    # fallback: from here the block counts as moving
PAD_SECONDS = 1.0         # extend sections by 1s each side (see find_suspect_sections)
CONFIDENT_NOISE_MULT = 20.0   # motion counts as certain from 20x the encoder noise floor
ABS_CONFIDENT_K1 = 1e-3       # fallback without a reference block: K1 above this = certain
UNCERTAIN_ACTION = 'correct'  # 'correct' | 'keep' - behaviour on an uncertain rate
DECODE_CHUNK = 900        # max. frames per decode call (RAM cap, 900 ~ 59MB@256px)


# ── Sektionen finden ─────────────────────────────────────────────────────────

def find_suspect_sections(fps_seq, source_fps,
                          min_seconds=MIN_SECONDS,
                          fps_suspect=FPS_SUSPECT,
                          fade_excluded=None,
                          pad_seconds=PAD_SECONDS):
    """
    Finds contiguous runs with fps <= fps_suspect lasting at least
    min_seconds. Frames excluded as fades do not count as suspicious - 0 fps
    is intended there.

    IMPORTANT - PADDING: the fps values come from a rolling 1s window. At the
    edge of a misdetected scene the value therefore falls off only gradually,
    i.e. the wrong dup_flags reach up to 1s FURTHER than the region with
    fps<=1. Without an extension that edge stays uncorrected and drags the
    result down (measured: a 29 fps residual error across the transition).
    Every section is therefore extended by pad_seconds on both sides, and
    overlapping sections are merged.

    Returns: a list of (start_idx, end_idx_exclusive).
    """
    fade_excluded = fade_excluded or set()
    min_len = max(1, int(round(min_seconds * source_fps)))

    runs, start = [], None
    for i, v in enumerate(fps_seq):
        suspect = (v is not None and i not in fade_excluded and v <= fps_suspect)
        if suspect and start is None:
            start = i
        elif not suspect and start is not None:
            if i - start >= min_len:
                runs.append((start, i))
            start = None
    if start is not None and len(fps_seq) - start >= min_len:
        runs.append((start, len(fps_seq)))

    if not runs:
        return []

    # Padding + Merge
    pad = int(round(pad_seconds * source_fps))
    n = len(fps_seq)
    padded = [(max(0, s - pad), min(n, e + pad)) for s, e in runs]
    merged = [padded[0]]
    for s, e in padded[1:]:
        ps, pe = merged[-1]
        if s <= pe:
            merged[-1] = (ps, max(pe, e))
        else:
            merged.append((s, e))
    return merged


# ── Decode ───────────────────────────────────────────────────────────────────

def _decode_section_gray(input_file, start_frame, n_frames, source_fps,
                         size=WORK_SIZE, use_nvdec=True):
    """
    Decodes [start_frame, start_frame+n_frames) as size x size greyscale.

    `flags=area` instead of `neighbor`: point sampling throws away individual
    pixels at a strong downscale and is effectively blind to subtle motion,
    while area averages correctly over the source block.

    Returns a list of float32 arrays (0..255).
    """
    if n_frames <= 0:
        return []

    variants = ([['-hwaccel', 'cuda'], []] if use_nvdec else [[]])
    fb = size * size

    for hw in variants:
        cmd = ['ffmpeg', '-v', 'error', *hw]
        if start_frame > 0 and source_fps > 0:
            cmd += ['-ss', f'{start_frame / source_fps:.6f}']
        cmd += ['-i', input_file,
                '-frames:v', str(n_frames),
                '-vf', f'scale={size}:{size}:flags=area,format=gray',
                '-f', 'rawvideo', '-']
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                    stderr=subprocess.DEVNULL,
                                    stdin=subprocess.DEVNULL)
            out = []
            while True:
                buf = b''
                while len(buf) < fb:
                    chunk = proc.stdout.read(fb - len(buf))
                    if not chunk:
                        break
                    buf += chunk
                if len(buf) < fb:
                    break
                out.append(np.frombuffer(buf, dtype=np.uint8)
                             .reshape(size, size).astype(np.float32))
            try:
                proc.kill()
            except Exception:
                pass
            if out:
                return out
        except Exception:
            continue
    return []


def _mad(a, b):
    """Mean absolute difference, normalised to 0..1."""
    return float(np.mean(np.abs(a - b)) / 255.0)


# ── Block-Entscheidung ───────────────────────────────────────────────────────

def classify_block(frames):
    """
    Decides for ONE ~1s block whether it is genuinely frozen.

    Returns a dict with:
        frozen    - True = 0 fps is correct
        flags     - per-frame duplicate flags for this block
        med_k1    - median neighbour diff (for the noise floor calibration)
        confident - True = the rate can be determined reliably
        reason    - plain text for the log
    """
    n = len(frames)
    if n < 2:
        return {'frozen': True, 'dup_flags': [True] * n, 'med_k1': 0.0,
                'clean_split': True, 'reason': 'zu kurz'}

    # ── Signal 3: einfarbig? ────────────────────────────────────────────
    med_std = float(np.median([f.std() for f in frames]))
    if med_std < UNIFORM_STD:
        return {'frozen': True, 'dup_flags': [True] * n, 'med_k1': 0.0,
                'clean_split': True,
                'reason': f'einfarbig (std={med_std:.2f})'}

    k1 = np.array([_mad(frames[i - 1], frames[i]) for i in range(1, n)],
                  dtype=np.float64)
    med_k1 = float(np.median(k1))

    # ── Signal 1: share of bit-identical neighbour pairs ────────────────
    near_zero = k1 < NEAR_ZERO_MAD
    frac_zero = float(near_zero.mean())

    if frac_zero >= DUP_FRAC_CONFIRM:
        # Mostly real duplicates -> 0 fps confirmed. Flags are still set per
        # frame: on 30fps footage that correctly gives ~50% instead of a flat 100%.
        flags = [True] + [bool(z) for z in near_zero]
        return {'frozen': True, 'dup_flags': flags, 'med_k1': med_k1,
                'clean_split': True,
                'reason': f'{frac_zero*100:.0f}% bit-identische Paare → echt eingefroren'}

    # ── Signal 2: growth across the time baseline (duplicates with noise) ──
    # Only meaningful when K1 is not already ~0 (see the module docstring).
    ratio = None
    if med_k1 > NEAR_ZERO_MAD:
        k_far = min(30, n - 1)
        if k_far >= 5:
            far = [_mad(frames[a], frames[a + k_far]) for a in range(0, n - k_far)]
            ratio = float(np.median(far)) / max(med_k1, 1e-12)
            if ratio < GROWTH_RATIO_MIN:
                return {'frozen': True, 'dup_flags': [True] * n, 'med_k1': med_k1,
                        'clean_split': True,
                        'reason': f'diff grows only {ratio:.2f}x across {k_far} frames '
                                  f'-> frozen image with noise'}

    # ── The block is in fact moving -> reclassify by distribution ───────
    flags = [False] + [bool(z) for z in near_zero]
    clean_split = bool(near_zero.any())

    if not clean_split:
        s = np.sort(k1)
        gaps = np.diff(s)
        if len(gaps):
            i = int(np.argmax(gaps))
            lower_top, upper_bot = s[i], s[i + 1]
            lower_frac = (i + 1) / len(s)
            if upper_bot >= lower_top * 3.0 and 0.05 <= lower_frac <= 0.95:
                thr = (lower_top + upper_bot) / 2.0
                flags = [False] + [bool(m < thr) for m in k1]
                clean_split = True

    dup_pct = 100.0 * sum(flags) / n
    r_txt = f', growth {ratio:.1f}x' if ratio is not None else ''
    return {'frozen': False, 'dup_flags': flags, 'med_k1': med_k1,
            'clean_split': clean_split,
            'reason': f'echte Bewegung ({frac_zero*100:.0f}% identische Paare{r_txt}) '
                      f'→ Duplikat-Rate {dup_pct:.0f}%'}


# ── Recompute fps/ft from dup_flags ──────────────────────────────────────────

def recompute_fps_from_flags(dup_flags, source_fps, fade_excluded=None):
    """
    Recomputes fps_seq/ft_seq from dup_flags - with exactly the window logic of
    the pre-pass (rolling 1s window, share of unique frames x source_fps).

    Deliberately over the WHOLE sequence: the window reaches up to 1s past a
    corrected section, so a purely local correction would leave a step at the
    Grenze springen.
    """
    import collections
    fade_excluded = fade_excluded or set()
    win = collections.deque(maxlen=int(source_fps))
    fps_seq, ft_seq = [], []
    last_eff = float(source_fps)

    for is_dup in dup_flags:
        win.append(not is_dup)
        ws = len(win)
        eff = (sum(win) / ws) * source_fps if ws >= 4 else last_eff
        eff = max(0.0, min(eff, source_fps))
        last_eff = eff
        fps_seq.append(eff)
        ft_seq.append(1000.0 / eff if eff > 0 else 1000.0)

    for i in fade_excluded:
        if 0 <= i < len(fps_seq):
            fps_seq[i] = None
            ft_seq[i] = None
    return fps_seq, ft_seq


# ── Orchestrierung ───────────────────────────────────────────────────────────

def run_verification_pass(input_file, fps_seq, ft_seq, dup_flags, source_fps,
                          actual_start=0, fade_excluded=None,
                          work_size=WORK_SIZE, use_nvdec=True,
                          uncertain_action=UNCERTAIN_ACTION,
                          progress_cb=None, log=print,
                          is_cancelled=lambda: False):
    """
    Main entry point. Re-checks every suspicious 0 fps section.

    uncertain_action - what happens to blocks recognised as moving whose RATE
        cannot be determined reliably (see the module docstring):
          'correct' - correct them anyway (closer to the truth in most cases,
                      but can set real 30fps footage too high)
          'keep'    - leave them at 0 fps (conservative)
        In both cases the affected time ranges are logged and listed in the
        report under 'uncertain'.

    Returns: (fps_seq, ft_seq, dup_flags, report)
    """
    fade_excluded = fade_excluded or set()
    report = {'sections': [], 'corrected_frames': 0, 'checked_frames': 0,
              'blocks_moving': 0, 'blocks_frozen': 0, 'uncertain': []}

    sections = find_suspect_sections(fps_seq, source_fps, fade_excluded=fade_excluded)
    if not sections:
        log("✅ Verification pass: no suspicious 0 fps sections")
        return fps_seq, ft_seq, dup_flags, report

    total = sum(e - s for s, e in sections)
    log(f"🔎 Verification pass: {len(sections)} suspicious section(s), "
        f"{total} Frames ({total/max(source_fps,1):.1f}s) @ {work_size}px AREA")

    dup_flags = list(dup_flags)
    block_len = max(4, int(round(source_fps)))
    done = 0

    # ── PHASE 1: classify every block, apply nothing yet ────────────────
    # Two phases, because the encoder noise floor is only known once a block
    # known to be frozen has been found - that one serves as the reference
    # for judging how certain the moving blocks are.
    pending = []   # (gpos, n_blk, result)
    for sec_s, sec_e in sections:
        if is_cancelled():
            break
        n_sec = sec_e - sec_s
        report['checked_frames'] += n_sec

        for chunk_off in range(0, n_sec, DECODE_CHUNK):
            if is_cancelled():
                break
            chunk_n = min(DECODE_CHUNK, n_sec - chunk_off)
            frames = _decode_section_gray(
                input_file, actual_start + sec_s + chunk_off, chunk_n,
                source_fps, size=work_size, use_nvdec=use_nvdec)

            if len(frames) < 2:
                log(f"   ⚠️ Decode failed at frame "
                    f"{sec_s + chunk_off}, range skipped")
                continue

            for b0 in range(0, len(frames), block_len):
                blk = frames[b0:b0 + block_len]
                if len(blk) < 2:
                    continue
                res = classify_block(blk)
                pending.append((sec_s + chunk_off + b0, len(blk), res))

            done += chunk_n
            if progress_cb:
                progress_cb(int(100 * done / max(1, total)),
                            f"Verifikation {done}/{total}")

    if not pending:
        log("⚠️ Verification pass: nothing could be evaluated")
        return fps_seq, ft_seq, dup_flags, report

    # ── Estimate the noise floor from blocks known to be frozen ─────────
    frozen_k1 = [r['med_k1'] for _, _, r in pending
                 if r['frozen'] and r['med_k1'] > 0]
    noise_floor = float(np.median(frozen_k1)) if frozen_k1 else None
    if noise_floor:
        log(f"   Encoder noise floor from {len(frozen_k1)} frozen block(s): "
            f"{noise_floor:.2e}")
    else:
        log(f"   No frozen reference block - judging certainty via "
            f"Absolutwert (Schwelle {ABS_CONFIDENT_K1:.0e})")

    # ── PHASE 2: anwenden ───────────────────────────────────────────────
    any_corrected = False
    for gpos, n_blk, res in pending:
        if res['frozen']:
            report['blocks_frozen'] += 1
            confident = True
        else:
            report['blocks_moving'] += 1
            # Certain when a clean duplicate cluster was found, OR when the
            # motion is clearly above the encoder noise.
            if res['clean_split']:
                confident = True
            elif noise_floor:
                confident = res['med_k1'] > noise_floor * CONFIDENT_NOISE_MULT
            else:
                confident = res['med_k1'] > ABS_CONFIDENT_K1

        t0 = gpos / max(source_fps, 1)
        if not res['frozen'] and not confident:
            report['uncertain'].append({'start': gpos, 'end': gpos + n_blk,
                                        'time_s': t0, 'med_k1': res['med_k1']})
            if uncertain_action == 'keep':
                log(f"   ❓ Block {gpos}-{gpos+n_blk} (t={t0:.1f}s): moving, but the rate "
                    f"is uncertain (K1={res['med_k1']:.1e} near the noise floor) -> kept at 0 fps")
                continue
            log(f"   ❓ Block {gpos}-{gpos+n_blk} (t={t0:.1f}s): moving, but the rate "
                f"is uncertain (K1={res['med_k1']:.1e} near the noise floor) -> corrected, please check")

        changed = 0
        for i, f in enumerate(res['dup_flags']):
            gi = gpos + i
            if 0 <= gi < len(dup_flags) and dup_flags[gi] != f:
                dup_flags[gi] = f
                changed += 1
        if changed:
            any_corrected = True
            report['corrected_frames'] += changed

        if res['frozen'] or confident:
            mark = "✓" if res['frozen'] else "⚠️"
            log(f"   {mark} Block {gpos}-{gpos+n_blk} (t={t0:.1f}s): {res['reason']}"
                + (f" [{changed} Frames korrigiert]" if changed else ""))

    if any_corrected:
        fps_seq, ft_seq = recompute_fps_from_flags(dup_flags, source_fps, fade_excluded)
        log(f"🔧 Verification pass: {report['corrected_frames']} frames corrected "
            f"({report['blocks_moving']} moving / {report['blocks_frozen']} frozen blocks), "
            f"fps/ft recomputed")
    else:
        log(f"✅ Verification pass: all {report['blocks_frozen']} blocks confirmed, "
            f"no correction needed")

    if report['uncertain']:
        times = ", ".join(f"{u['time_s']:.1f}s" for u in report['uncertain'][:8])
        more = "" if len(report['uncertain']) <= 8 else f" (+{len(report['uncertain'])-8} weitere)"
        log(f"❓ {len(report['uncertain'])} block(s) with an uncertain rate at: {times}{more}")

    return fps_seq, ft_seq, dup_flags, report
