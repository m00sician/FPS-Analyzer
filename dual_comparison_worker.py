"""
Dual Comparison Worker - combined side-by-side video with a shared FPS graph.

Pipeline:
  1. Analyse video A  -> per-frame fps_a[], ft_a[], decoded_frames_a[]  (RAM)
  2. Analyse video B  -> per-frame fps_b[], ft_b[], decoded_frames_b[]  (RAM)
  3. Render combined:
       - left  = crop/resize frame_a[i]
       - right = crop/resize frame_b[i]
       - graph = dual FPS graph (line A + line B, full width)
       - encode(hstack(left, right) + graph)

Memory: ~2 x video_frames x frame_bytes
4K 60fps 60s = 2 x 3600 x 24MB is not feasible, so this works frame by frame
instead of buffering in RAM: an analysis pass (FPS data only) followed by a
render pass that reads the videos again.
"""

import os
import cv2
import numpy as np
import collections
from PyQt6.QtCore import QThread, pyqtSignal

# ── Bebas Neue font helper ────────────────────────────────────────────────────

def _get_bebas_path() -> str | None:
    candidates = [
        "C:/Windows/Fonts/BebasNeue-Regular.ttf",
        "C:/Windows/Fonts/BebasNeue.ttf",
        os.path.join(os.path.dirname(__file__), "fonts", "BebasNeue-Regular.ttf"),
        "/usr/share/fonts/truetype/bebas/BebasNeue-Regular.ttf",
        os.path.expanduser("~/.fonts/BebasNeue-Regular.ttf"),
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    return None

_BEBAS_PATH = _get_bebas_path()
_font_cache: dict = {}

def _get_font(size: int):
    """Return a Pillow ImageFont for Bebas Neue at given size, cached."""
    if size in _font_cache:
        return _font_cache[size]
    try:
        from PIL import ImageFont
        if _BEBAS_PATH:
            font = ImageFont.truetype(_BEBAS_PATH, size)
        else:
            font = ImageFont.load_default()
        _font_cache[size] = font
        return font
    except Exception:
        return None

def _draw_text_bebas(img: np.ndarray, text: str, x: int, y: int,
                     size: int, color: tuple = (255, 255, 255),
                     shadow: bool = False, outline: bool = True,
                     outline_width: int = None) -> np.ndarray:
    """
    Draw text with Bebas Neue (Pillow) onto a numpy BGR image.
    outline=True draws a black stroke around the glyphs (no offset shadow).
    Falls back to cv2.putText if Pillow/font not available.
    """
    try:
        from PIL import Image as PILImage, ImageDraw as PILDraw
        font = _get_font(size)
        if font is None:
            raise RuntimeError("no font")

        h, w = img.shape[:2]
        pad = size + 8
        rx1 = max(0, x - pad)
        ry1 = max(0, y - size - pad)
        rx2 = min(w, x + size * len(text) + pad)
        ry2 = min(h, y + size + pad)
        if rx2 <= rx1 or ry2 <= ry1:
            return img

        roi_bgr = img[ry1:ry2, rx1:rx2]
        roi_rgb = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2RGB)
        pil = PILImage.fromarray(roi_rgb)
        draw = PILDraw.Draw(pil)

        lx, ly = x - rx1, y - ry1
        rgb_color = (color[2], color[1], color[0])  # BGR → RGB

        sw = outline_width if outline_width is not None else max(2, size // 16)

        if shadow:
            draw.text((lx + sw, ly + sw), text, font=font,
                      fill=(0, 0, 0), stroke_width=sw, stroke_fill=(0, 0, 0))

        if outline:
            draw.text((lx, ly), text, font=font, fill=rgb_color,
                      stroke_width=sw, stroke_fill=(0, 0, 0))
        else:
            draw.text((lx, ly), text, font=font, fill=rgb_color)

        img[ry1:ry2, rx1:rx2] = cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)
        return img
    except Exception:
        fs = max(0.4, size / 40)
        cv2.putText(img, text, (x + 1, y + 1), cv2.FONT_HERSHEY_SIMPLEX,
                    fs, (0, 0, 0), max(3, int(fs * 5)), cv2.LINE_AA)
        cv2.putText(img, text, (x, y), cv2.FONT_HERSHEY_SIMPLEX,
                    fs, color, max(1, int(fs * 2)), cv2.LINE_AA)
        return img


# ── Analysis-only pass ────────────────────────────────────────────────────────

class VideoAnalyzer:
    """
    Lightweight analysis pass — identical duplicate-detection logic as AnalysisWorker
    but only collects per-frame fps/frametime data, no encoding.
    """

    def __init__(self, video_path: str, settings: dict, progress_cb=None, cancel_check=None):
        self.video_path = video_path
        self.settings = settings
        self.progress_cb = progress_cb      # (frame, total) -> None
        self.cancel_check = cancel_check    # () -> bool

        self.fps_per_frame: list[float] = []
        self.ft_per_frame: list[float] = []
        self.source_fps: float = 0.0
        self.source_width: int = 0
        self.source_height: int = 0
        self.total_frames: int = 0

    def analyze(self) -> bool:
        """Run analysis. Returns True on success."""
        cap = cv2.VideoCapture(self.video_path)
        if not cap.isOpened():
            return False

        self.source_fps    = cap.get(cv2.CAP_PROP_FPS) or 60.0
        self.source_width  = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.source_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        self.total_frames  = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

        diff_threshold   = self.settings.get('diff_threshold', 0.005)
        window_size      = max(1, int(self.source_fps))

        # Tile-based detection with an adaptive threshold (see frame_detection.py)
        from frame_detection import TileAdaptiveDetector
        detector = TileAdaptiveDetector(diff_threshold)

        # Rolling duplicate window
        unique_window = collections.deque(maxlen=window_size)
        effective_fps = self.source_fps

        fps_history   = collections.deque(maxlen=180)
        fps_calc_win  = collections.deque(maxlen=max(1, window_size // 4))
        displayed_fps = self.source_fps

        frame_num = 0
        while True:
            if self.cancel_check and self.cancel_check():
                cap.release()
                return False

            ret, frame = cap.read()
            if not ret:
                break
            frame_num += 1

            # Downsample for diff
            gray = cv2.cvtColor(
                cv2.resize(frame, (128, 128), interpolation=cv2.INTER_NEAREST),
                cv2.COLOR_BGR2GRAY
            ).astype(np.float32) / 255.0

            is_dup, _score = detector.process(gray)

            unique_window.append(0 if is_dup else 1)

            if len(unique_window) >= window_size // 2:
                unique_in_window = sum(unique_window)
                effective_fps = (unique_in_window / len(unique_window)) * self.source_fps
                effective_fps = max(0.0, min(effective_fps, self.source_fps))
            
            current_ft = 1000.0 / effective_fps if effective_fps > 0 else 1000.0

            fps_history.append(effective_fps)
            fps_calc_win.append(effective_fps)
            if len(fps_calc_win) >= max(1, window_size // 4):
                displayed_fps = round(sum(fps_calc_win) / len(fps_calc_win))

            self.fps_per_frame.append(effective_fps)
            self.ft_per_frame.append(current_ft)

            if self.progress_cb and frame_num % 30 == 0:
                self.progress_cb(frame_num, self.total_frames)

        cap.release()
        return len(self.fps_per_frame) > 0


# ── Dual graph renderer ───────────────────────────────────────────────────────

def render_dual_fps_graph(
    overlay: np.ndarray,
    fps_a: list, fps_b: list,
    label_a: str, label_b: str,
    color_a: tuple, color_b: tuple,
    gx: int, gy: int, gw: int, gh: int,
    max_fps: float,
    line_thick: int = 3,
    bg_alpha: float = 0.55,
    playhead_index: int = None,
    frosted: bool = False,
    frost_blur: int = 25,
    frost_darken: float = 0.35,
) -> np.ndarray:
    """
    Draw dual FPS graph on overlay at (gx, gy, gw, gh).
    With playhead_index set, this draws DF style: fps_a/fps_b are the FULL
    sequences and the window is centred on playhead_index (past on the left,
    future on the right, centre line marked). Otherwise it is a rolling window
    over the last MAX_POINTS.
    """
    h, w = overlay.shape[:2]
    n_sections = 4
    MAX_POINTS = 180

    # Background - frosted glass or solid fill
    x1, y1, x2, y2 = gx, gy, min(gx + gw, w), min(gy + gh, h)
    if frosted:
        try:
            from code_renderer import _apply_frosted_glass
            _apply_frosted_glass(overlay, gx, gy, gw, gh,
                                 blur_strength=frost_blur, darken=frost_darken)
        except Exception:
            roi = overlay[y1:y2, x1:x2].astype(np.float32)
            overlay[y1:y2, x1:x2] = (roi * (1 - bg_alpha)).astype(np.uint8)
    else:
        roi = overlay[y1:y2, x1:x2].astype(np.float32)
        bg = np.zeros_like(roi)
        alpha = bg_alpha
        overlay[y1:y2, x1:x2] = (roi * (1 - alpha) + bg * alpha).astype(np.uint8)

    # (The border is drawn AFTER the lines - see below - so it hides where the
    #  lines start and overshoot, same as in the main analysis.)

    # Grid lines
    line_t = max(1, gh // 150)
    for i in range(n_sections + 1):
        ly = gy + int(i * gh / n_sections)
        if 0 <= ly < h:
            overlay[max(0, ly - line_t // 2):min(h, ly + line_t // 2 + 1), gx:min(gx + gw, w)] = \
                np.clip(
                    overlay[max(0, ly - line_t // 2):min(h, ly + line_t // 2 + 1), gx:min(gx + gw, w)].astype(np.float32) * 0.3
                    + np.array([200, 200, 200]) * 0.7, 0, 255
                ).astype(np.uint8)

    # Axis labels (right side) — smaller, outline only, 20px from graph
    s4k = h / 2160.0
    label_x = gx + gw + max(8, int(20 * s4k))
    scale = min(w / 1920, h / 1080)
    lsize_px = max(14, int(46 * s4k))
    for pos_idx, lbl in [(0, str(int(max_fps))), (2, str(int(max_fps // 2))), (4, '0')]:
        ly_lbl = gy + int(pos_idx * gh / n_sections)
        text_top = ly_lbl - lsize_px // 2
        text_top = max(0, min(h - lsize_px - 2, text_top))
        if label_x < w:
            _draw_text_bebas(overlay, lbl, label_x, text_top,
                             lsize_px, (255, 255, 255), shadow=False, outline=True)

    # FRAME RATE title — fully ABOVE the graph box
    title_px = max(24, int(64 * s4k))
    title_y  = max(0, gy - title_px - max(4, int(8 * s4k)))
    _draw_text_bebas(overlay, 'FRAME RATE', gx, title_y, title_px,
                     (255, 255, 255), shadow=False, outline=True)

    def _draw_line(seq, color):
        if not seq:
            return
        s4k_l = h / 2160.0
        line_x0  = gx + max(1, int(4 * s4k_l))
        # The line ends at the right edge of the graph (minus a small margin),
        # NOT beyond it - same as in the main analysis.
        line_end = gx + gw - max(2, int(5 * s4k_l))
        line_w   = line_end - line_x0
        top_pad  = max(3, int(10 * s4k_l))

        if playhead_index is not None:
            # DF style: a centred window over the full sequence
            half = MAX_POINTS // 2
            total = 2 * half + 1
            raw = np.full(total, np.nan, dtype=np.float32)
            valid = np.zeros(total, dtype=bool)
            n = len(seq)
            for j in range(total):
                src = playhead_index - half + j
                if 0 <= src < n:
                    v = seq[src]
                    if v is not None and not (isinstance(v, float) and np.isnan(v)):
                        raw[j] = v
                        valid[j] = True
            indices = np.arange(total, dtype=np.float32)
            px_arr = np.clip((line_x0 + indices * line_w / (total - 1)).astype(np.int32),
                             line_x0, min(line_end, w - 1))
            safe = np.where(valid, raw, 0.0)
            vals = np.clip(safe / max(max_fps, 1), 0.0, 1.0)
            py_arr = np.clip((gy + top_pad + (1.0 - vals) * (gh - top_pad)).astype(np.int32),
                             gy, gy + gh - 1)
            # Draw segment by segment (gaps where values are invalid)
            sx, sy = [], []
            for k in range(total):
                if valid[k]:
                    sx.append(px_arr[k]); sy.append(py_arr[k])
                else:
                    if len(sx) >= 2:
                        pts = np.stack([sx, sy], axis=1).reshape((-1,1,2)).astype(np.int32)
                        cv2.polylines(overlay, [pts], False, color, line_thick, cv2.LINE_AA)
                    sx, sy = [], []
            if len(sx) >= 2:
                pts = np.stack([sx, sy], axis=1).reshape((-1,1,2)).astype(np.int32)
                cv2.polylines(overlay, [pts], False, color, line_thick, cv2.LINE_AA)
            return

        # Rollendes Fenster (Fallback)
        n = len(seq)
        if n < 2:
            return
        hist = list(seq[-MAX_POINTS:]) if n > MAX_POINTS else list(seq)
        n_pts = len(hist)
        indices = np.arange(n_pts, dtype=np.float32)
        px_arr = np.clip((line_x0 + indices * line_w / MAX_POINTS).astype(np.int32), line_x0, min(line_end, w - 1))
        vals   = np.clip(np.array(hist, dtype=np.float32) / max(max_fps, 1), 0.0, 1.0)
        py_arr = np.clip((gy + top_pad + (1.0 - vals) * (gh - top_pad)).astype(np.int32), gy, gy + gh - 1)
        pts    = np.stack([px_arr, py_arr], axis=1).reshape((-1, 1, 2))
        cv2.polylines(overlay, [pts], False, color, line_thick, cv2.LINE_AA)

    _draw_line(fps_a, color_a)
    _draw_line(fps_b, color_b)

    # Playhead-Mittellinie
    if playhead_index is not None:
        cx = gx + gw // 2
        pth = max(1, int(2 * (h / 2160.0)))
        roi_ph = overlay[gy:gy+gh, max(0, cx-pth//2):cx+pth//2+1].astype(np.float32)
        overlay[gy:gy+gh, max(0, cx-pth//2):cx+pth//2+1] = \
            (roi_ph * 0.25 + np.full_like(roi_ph, 255) * 0.75).astype(np.uint8)

    # White outline - drawn LAST, ON TOP of the lines, so the line start and
    # overshoot at the edge are hidden. 1px thicker than before.
    ot = max(2, gh // 100) + 1
    for i, coords in enumerate([
        (gx, gy, gx + gw, gy + ot),
        (gx, gy + gh - ot, gx + gw, gy + gh),
        (gx, gy, gx + ot, gy + gh),
        (gx + gw - ot, gy, gx + gw, gy + gh),
    ]):
        cx1, cy1, cx2, cy2 = coords
        cx1 = max(0, min(cx1, w)); cx2 = max(0, min(cx2, w))
        cy1 = max(0, min(cy1, h)); cy2 = max(0, min(cy2, h))
        if cx2 > cx1 and cy2 > cy1:
            roi2 = overlay[cy1:cy2, cx1:cx2].astype(np.float32)
            overlay[cy1:cy2, cx1:cx2] = np.clip(
                roi2 * 0.15 + np.array([255, 255, 255]) * 0.85, 0, 255
            ).astype(np.uint8)

    return overlay


def render_fps_number(overlay: np.ndarray, fps: float, x: int, y: int,
                      color: tuple, scale: float) -> np.ndarray:
    """Draw FPS number with Bebas Neue font, black outline. y = top edge."""
    text    = str(int(round(fps))) if fps >= 0 else "---"
    size_px = max(60, int(130 * scale))
    return _draw_text_bebas(overlay, text, x, y, size_px, color,
                            shadow=False, outline=True)


# ── Combined render pass ──────────────────────────────────────────────────────

def render_combined_video(
    path_a: str, path_b: str,
    fps_a: list, fps_b: list,
    label_a: str, label_b: str,
    output_path: str,
    out_w: int, out_h: int,
    source_fps: float,
    bitrate: int,
    color_a: tuple, color_b: tuple,
    viewport_a: float = 0.5,
    viewport_b: float = 0.5,
    progress_cb=None,
    cancel_check=None,
    preview_cb=None,
    frosted: bool = False,
    frost_blur: int = 25,
    frost_darken: float = 0.35,
) -> bool:
    """
    Second pass: read both videos frame-by-frame, compose side-by-side,
    draw dual graph, encode to output_path.
    """
    cap_a = cv2.VideoCapture(path_a)
    cap_b = cv2.VideoCapture(path_b)
    if not cap_a.isOpened() or not cap_b.isOpened():
        return False

    total_a = int(cap_a.get(cv2.CAP_PROP_FRAME_COUNT))
    total_b = int(cap_b.get(cv2.CAP_PROP_FRAME_COUNT))
    total   = min(total_a, total_b, len(fps_a), len(fps_b))

    # Output dimensions — no extra canvas, graph overlays directly on video
    combined_w = out_w * 2
    combined_h = out_h
    scale      = min(out_w / 1920, out_h / 1080)

    # Graph geometry — 4K reference: 350px tall, 3720px wide, 50px from left/bottom
    s4k     = out_h / 2160.0
    graph_h = max(100, int(460 * s4k))
    margin  = max(15, int(50 * s4k))
    graph_x = margin
    graph_y = out_h - graph_h - margin
    graph_w = min(int(3740 * combined_w / 3840), combined_w - graph_x - max(30, int(90 * s4k)))

    # VideoWriter
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    writer = cv2.VideoWriter(output_path, fourcc, source_fps, (combined_w, combined_h))
    if not writer.isOpened():
        cap_a.release(); cap_b.release()
        return False

    # FPS number positions — 50px from left/top (4K reference)
    fps_num_scale = s4k * 1.4
    fps_num_y     = max(15, int(50 * s4k))
    fps_a_x       = max(15, int(50 * s4k))
    fps_b_x       = out_w + max(15, int(50 * s4k))

    # Rolling graph histories (last MAX_POINTS frames)
    MAX_POINTS = 180
    history_a: collections.deque = collections.deque(maxlen=MAX_POINTS)
    history_b: collections.deque = collections.deque(maxlen=MAX_POINTS)
    max_fps = max(max(fps_a, default=60), max(fps_b, default=60), 60.0)

    # The displayed FPS number is smoothed as in the main analysis:
    # Quarter-second window, rounded - instead of raw per-frame values
    disp_win = max(1, int(source_fps // 4))
    disp_buf_a: collections.deque = collections.deque(maxlen=disp_win)
    disp_buf_b: collections.deque = collections.deque(maxlen=disp_win)
    displayed_a = 0.0
    displayed_b = 0.0

    for frame_idx in range(total):
        if cancel_check and cancel_check():
            break

        ret_a, raw_a = cap_a.read()
        ret_b, raw_b = cap_b.read()
        if not ret_a or not ret_b:
            break

        # Resize/crop each video to out_w × out_h
        def _fit(frame, tw, th, viewport: float):
            fh, fw = frame.shape[:2]
            # Scale to fill height first
            scale_h = th / fh
            nw = int(fw * scale_h)
            nh = th
            resized = cv2.resize(frame, (nw, nh), interpolation=cv2.INTER_LINEAR)
            if nw >= tw:
                # Crop: viewport 0.0 = left edge, 1.0 = right edge
                max_x0 = nw - tw
                x0 = int(viewport * max_x0)
                return resized[:, x0:x0 + tw]
            else:
                # Video narrower than target — pad with black
                out = np.zeros((th, tw, 3), dtype=np.uint8)
                x0 = (tw - nw) // 2
                out[:, x0:x0 + nw] = resized
                return out

        left  = _fit(raw_a, out_w, out_h, viewport_a)
        right = _fit(raw_b, out_w, out_h, viewport_b)

        # Combined canvas — exactly video height, no extra space
        canvas = np.zeros((combined_h, combined_w, 3), dtype=np.uint8)
        canvas[:out_h, :out_w]  = left
        canvas[:out_h, out_w:]  = right

        # Divider line
        canvas[:out_h, out_w - 1:out_w + 1] = [40, 40, 40]

        # RGB for overlay rendering
        try:
            canvas_rgb = cv2.cvtColor(canvas, cv2.COLOR_BGR2RGB)

            # Update rolling histories
            cur_fps_a = fps_a[frame_idx] if frame_idx < len(fps_a) else 0.0
            cur_fps_b = fps_b[frame_idx] if frame_idx < len(fps_b) else 0.0
            history_a.append(cur_fps_a)
            history_b.append(cur_fps_b)

            # Display smoothing: averaged over disp_win, then rounded
            disp_buf_a.append(cur_fps_a)
            disp_buf_b.append(cur_fps_b)
            displayed_a = round(sum(disp_buf_a) / len(disp_buf_a))
            displayed_b = round(sum(disp_buf_b) / len(disp_buf_b))

            # Graph-Linien gehen via cv2.polylines DIREKT aufs RGB-Canvas
            # (no internal colour swap like _draw_text_bebas does) so the BGR
            # colours are turned into RGB here, or A/B would look swapped.
            color_a_rgb = (int(color_a[2]), int(color_a[1]), int(color_a[0]))
            color_b_rgb = (int(color_b[2]), int(color_b[1]), int(color_b[0]))

            # Draw dual graph — DF-Playhead-Stil (volle Sequenzen + aktueller Index)
            render_dual_fps_graph(
                canvas_rgb, fps_a, fps_b,
                label_a, label_b,
                color_a_rgb, color_b_rgb,
                graph_x, graph_y, graph_w, graph_h,
                max_fps=max_fps,
                line_thick=max(2, int(3 * scale)),
                bg_alpha=0.55,
                playhead_index=frame_idx,
                frosted=frosted,
                frost_blur=int(frost_blur),
                frost_darken=float(frost_darken),
            )

            render_fps_number(canvas_rgb, displayed_a, fps_a_x, fps_num_y, color_a_rgb, fps_num_scale)
            render_fps_number(canvas_rgb, displayed_b, fps_b_x, fps_num_y, color_b_rgb, fps_num_scale)

            out_bgr = cv2.cvtColor(canvas_rgb, cv2.COLOR_RGB2BGR)
            writer.write(out_bgr)
            # Vorschau-Frame gelegentlich weiterreichen
            if preview_cb is not None and frame_idx % 30 == 0:
                try:
                    preview_cb(out_bgr)
                except Exception:
                    pass
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"⚠️ Render error frame {frame_idx}: {e}")
            writer.write(canvas)  # write raw frame without overlay

        if progress_cb and frame_idx % 30 == 0:
            progress_cb(frame_idx, total)

    cap_a.release()
    cap_b.release()
    writer.release()

    # Re-encode with ffmpeg for proper mp4 container + bitrate
    # NVENC (RTX GPU) first, libx264 as the fallback
    try:
        import subprocess
        tmp = output_path + '_tmp.mp4'
        os.rename(output_path, tmp)
        br = f"{bitrate}M"

        result = subprocess.run(
            ['ffmpeg', '-y', '-i', tmp,
             '-c:v', 'h264_nvenc', '-b:v', br, '-preset', 'p4',
             '-movflags', '+faststart', output_path],
            capture_output=True, timeout=600
        )
        if result.returncode != 0:
            print("⚠️ NVENC not available, falling back to libx264")
            result = subprocess.run(
                ['ffmpeg', '-y', '-i', tmp,
                 '-c:v', 'libx264', '-b:v', br, '-preset', 'fast',
                 '-movflags', '+faststart', output_path],
                capture_output=True, timeout=600
            )
        else:
            print("🚀 NVENC encode (GPU)")

        if result.returncode == 0 and os.path.exists(output_path):
            os.unlink(tmp)
        else:
            os.rename(tmp, output_path)   # fallback: keep raw mp4v
    except Exception:
        # ffmpeg not available — raw mp4v output still works
        try:
            if os.path.exists(tmp) and not os.path.exists(output_path):
                os.rename(tmp, output_path)
        except Exception:
            pass

    return os.path.exists(output_path)


# ── QThread worker ────────────────────────────────────────────────────────────

class DualComparisonWorker(QThread):
    """
    Full dual-comparison pipeline as a QThread.

    Signals:
        progress(phase, percent, message)
        finished(success, message)
        preview(label, frame_bgr)
    """
    progress = pyqtSignal(str, int, str)
    finished = pyqtSignal(bool, str)
    preview  = pyqtSignal(str, np.ndarray)

    # Color A = blue (BGR), Color B = orange (BGR)
    COLOR_A = (220, 120, 50)
    COLOR_B = (50, 140, 255)

    def __init__(self, path_a: str, path_b: str,
                 name_a: str, name_b: str,
                 output_dir: str, settings: dict):
        super().__init__()
        self.path_a    = path_a
        self.path_b    = path_b
        self.name_a    = name_a
        self.name_b    = name_b
        self.output_dir = output_dir
        self.settings  = settings
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        try:
            self._run()
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.finished.emit(False, f"❌ Error: {e}")
        finally:
            # Ensure Qt knows thread is done
            pass

    def _run(self):
        settings  = self.settings
        res_w, res_h = settings.get('comparison_resolution', (960, 1080))
        bitrate      = settings.get('bitrate', 50)
        threshold    = settings.get('diff_threshold', 0.005)

        # ── Phase 1: analyse video A ──────────────────────────────────────────
        self.progress.emit("Analysis", 0, f"🔍 Analysing {self.name_a}...")

        def prog_a(f, t):
            pct = int(f / max(t, 1) * 40)   # 0-40%
            self.progress.emit("Analysis", pct, f"Analysing {self.name_a}: {f}/{t}")

        analyzer_a = VideoAnalyzer(
            self.path_a,
            {'diff_threshold': threshold},
            progress_cb=prog_a,
            cancel_check=lambda: self._cancelled,
        )
        if not analyzer_a.analyze() or self._cancelled:
            self.finished.emit(False, "❌ Analysis of video A failed or was cancelled")
            return

        self.progress.emit("Analysis", 40, f"✅ {self.name_a} analysed ({len(analyzer_a.fps_per_frame)} frames)")

        # ── Phase 2: analyse video B ──────────────────────────────────────────
        self.progress.emit("Analysis", 40, f"🔍 Analysing {self.name_b}...")

        def prog_b(f, t):
            pct = 40 + int(f / max(t, 1) * 40)   # 40-80%
            self.progress.emit("Analysis", pct, f"Analysing {self.name_b}: {f}/{t}")

        analyzer_b = VideoAnalyzer(
            self.path_b,
            {'diff_threshold': threshold},
            progress_cb=prog_b,
            cancel_check=lambda: self._cancelled,
        )
        if not analyzer_b.analyze() or self._cancelled:
            self.finished.emit(False, "❌ Analysis of video B failed or was cancelled")
            return

        self.progress.emit("Analysis", 80, f"✅ {self.name_b} analysed ({len(analyzer_b.fps_per_frame)} frames)")

        # ── Phase 3: Render ───────────────────────────────────────────────────
        out_name = f"{self.name_a}_vs_{self.name_b}_comparison.mp4"
        out_name = out_name.replace(' ', '_').replace('/', '_')
        output_path = os.path.join(self.output_dir, out_name)

        source_fps = analyzer_a.source_fps

        # Viewport offsets (0.0 = left edge, 1.0 = right edge)
        viewport_a = settings.get('viewport_a', 0.5)
        viewport_b = settings.get('viewport_b', 0.5)

        # Line/FPS colors (BGR) — user-selectable, defaults to class constants
        color_a = tuple(settings.get('color_a', self.COLOR_A))
        color_b = tuple(settings.get('color_b', self.COLOR_B))

        def prog_render(f, t):
            pct = 80 + int(f / max(t, 1) * 20)   # 80-100%
            self.progress.emit("Rendern", pct, f"Rendere kombiniertes Video: {f}/{t}")

        self.progress.emit("Rendern", 80, "🎬 Rendere kombiniertes Video...")

        ok = render_combined_video(
            path_a=self.path_a,
            path_b=self.path_b,
            fps_a=analyzer_a.fps_per_frame,
            fps_b=analyzer_b.fps_per_frame,
            label_a=self.name_a,
            label_b=self.name_b,
            output_path=output_path,
            out_w=res_w,
            out_h=res_h,
            source_fps=source_fps,
            bitrate=bitrate,
            color_a=color_a,
            color_b=color_b,
            viewport_a=viewport_a,
            viewport_b=viewport_b,
            progress_cb=prog_render,
            cancel_check=lambda: self._cancelled,
            preview_cb=lambda fb: self.preview.emit("Comparison", fb),
            frosted=settings.get('frosted_glass', False),
            frost_blur=int(settings.get('frost_blur', 25)),
            frost_darken=float(settings.get('frost_darken', 0.35)),
        )

        if self._cancelled:
            self.finished.emit(False, "❌ Abgebrochen")
            return

        if ok:
            size_mb = os.path.getsize(output_path) / 1024**2
            msg = (
                f"✅ Kombinations-Video erstellt!\n\n"
                f"📁 {output_path}\n"
                f"📊 {analyzer_a.total_frames} Frames · "
                f"{res_w * 2}×{res_h} · {source_fps:.1f} fps\n"
                f"💾 {size_mb:.1f} MB"
            )
            self.finished.emit(True, msg)
        else:
            self.finished.emit(False, f"❌ Could not create the output file:\n{output_path}")
