import collections
import cv2
import numpy as np
# CUDAResizer disabled for resize: GPU transfer overhead > CPU savings at 4K.
# INTER_LINEAR on CPU is ~24ms; torch interpolate incl. transfers is ~51ms.
_cuda_resizer = None
import subprocess
import os
import json
import multiprocessing
import time
from queue import Queue
from threading import Thread, Lock
from PyQt6.QtCore import QThread, pyqtSignal

# CUDA accelerator for GPU-accelerated frame analysis
try:
    from cuda_accelerator import get_cuda_analyzer, TORCH_CUDA_AVAILABLE
    CUDA_ACCELERATOR_AVAILABLE = True
    print("✅ CUDA Accelerator module loaded")
except ImportError:
    CUDA_ACCELERATOR_AVAILABLE = False
    TORCH_CUDA_AVAILABLE = False
    print("⚠️ CUDA Accelerator not available, using CPU")

class IncrementalStats:
    """Computes MIN/MAX/AVG incrementally in O(1) per update."""
    def __init__(self, warmup_frames=60):
        self.warmup_frames = warmup_frames
        self.count = 0
        self.total_count = 0
        self._sum = 0.0
        self._min = float('inf')
        self._max = float('-inf')
    
    def update(self, value):
        self.total_count += 1
        if self.total_count <= self.warmup_frames:
            return
        self.count += 1
        self._sum += value
        if value < self._min:
            self._min = value
        if value > self._max:
            self._max = value
    
    def get_stats(self):
        if self.count == 0:
            return {'avg': -1, 'min': -1, 'max': -1}
        return {'avg': self._sum / self.count, 'min': self._min, 'max': self._max}

def resize_with_aspect_ratio(frame, target_width, target_height, background_color=(0, 0, 0)):
    """
    Resize frame while preserving aspect ratio and adding letterboxing/pillarboxing
    """
    h0, w0 = frame.shape[:2]
    if w0 == target_width and h0 == target_height:
        return frame
    h, w = frame.shape[:2]
    
    # Calculate aspect ratios
    source_aspect = w / h
    target_aspect = target_width / target_height
    
    if source_aspect > target_aspect:
        # Source is wider - fit to width, add black bars top/bottom (letterbox)
        new_width = target_width
        new_height = int(target_width / source_aspect)
        
        # Resize to fit width
        resized = (_cuda_resizer.resize(frame, (new_width, new_height))
                   if _cuda_resizer else
                   cv2.resize(frame, (new_width, new_height)))
        
        # Create target canvas with black background
        result = np.full((target_height, target_width, 3), background_color, dtype=np.uint8)
        
        # Center the resized frame vertically
        y_offset = (target_height - new_height) // 2
        result[y_offset:y_offset + new_height, 0:target_width] = resized
        
    else:
        # Source is taller - fit to height, add black bars left/right (pillarbox)
        new_height = target_height
        new_width = int(target_height * source_aspect)
        
        # Resize to fit height
        resized = (_cuda_resizer.resize(frame, (new_width, new_height))
                   if _cuda_resizer else
                   cv2.resize(frame, (new_width, new_height)))
        
        # Create target canvas with black background
        result = np.full((target_height, target_width, 3), background_color, dtype=np.uint8)
        
        # Center the resized frame horizontally
        x_offset = (target_width - new_width) // 2
        result[0:target_height, x_offset:x_offset + new_width] = resized
    
    return result

def adaptive_crop_and_resize(frame, target_width, target_height, comparison_mode=False):
    # Source == target -> skip the resize entirely (saves ~8ms/frame at 4K->4K)
    h0, w0 = frame.shape[:2]
    if w0 == target_width and h0 == target_height:
        return frame
    """
    Adaptive Crop+Resize Logic for Comparison Mode with Proper Aspect Ratio
    """
    h, w = frame.shape[:2]
    
    if comparison_mode:
        # Log only once per video
        if not hasattr(adaptive_crop_and_resize, '_logged'):
            print(f"Comparison mode: Cropping {w}x{h} → {target_width}x{target_height}")
            adaptive_crop_and_resize._logged = True
        
        target_aspect = target_width / target_height
        source_aspect = w / h
        
        if source_aspect > target_aspect:
            crop_height = h
            crop_width = int(h * target_aspect)
            crop_x_start = (w - crop_width) // 2
            crop_x_end = crop_x_start + crop_width
            crop_y_start = 0
            crop_y_end = h
        else:
            crop_width = w
            crop_height = int(w / target_aspect)
            crop_x_start = 0
            crop_x_end = w
            crop_y_start = (h - crop_height) // 2
            crop_y_end = crop_y_start + crop_height
        
        frame_cropped = frame[crop_y_start:crop_y_end, crop_x_start:crop_x_end]
        # INTER_LINEAR: ~3× faster than LANCZOS4, negligible quality difference at video resolution
        frame_final = cv2.resize(frame_cropped, (target_width, target_height),
                                 interpolation=cv2.INTER_LINEAR)
        
        return frame_final
    else:
        return resize_with_aspect_ratio(frame, target_width, target_height)

_nvenc_probe_result = None
_nvenc_hevc_result = None

def _probe_nvenc(codec='h264') -> bool:
    """Checks whether ffmpeg + NVENC (h264/hevc) are available (~200ms, cached)."""
    global _nvenc_probe_result, _nvenc_hevc_result
    enc = 'hevc_nvenc' if codec == 'h265' else 'h264_nvenc'
    cached = _nvenc_hevc_result if codec == 'h265' else _nvenc_probe_result
    if cached is not None:
        return cached
    try:
        r = subprocess.run(
            ['ffmpeg', '-y', '-f', 'lavfi', '-i', 'color=black:s=320x180:d=0.1',
             '-c:v', enc, '-f', 'null', '-'],
            capture_output=True, timeout=15)
        ok = (r.returncode == 0)
    except Exception:
        ok = False
    if codec == 'h265':
        _nvenc_hevc_result = ok
    else:
        _nvenc_probe_result = ok
    print(f"🔎 NVENC probe ({enc}): {'✅ available' if ok else '❌ not available'}")
    return ok


class FFmpegPipeWriter:
    """
    Writes BGR frames straight into an ffmpeg encode process (stdin pipe).
    That removes the intermediate MJPEG encode, the intermediate file and the
    final re-encode pass completely. API compatible with cv2.VideoWriter
    (write / release / isOpened).
    """
    def __init__(self, output_path, width, height, fps, mode, use_nvenc=True,
                 codec_family='h265', quality_preset='p6', in_pix_fmt='bgr24'):
        """
        mode: 'cq' (quality, CQ ~18) or an int (bitrate in Mbps).
        codec_family: 'h265' (HEVC, recommended for 4K) or 'h264'.
        quality_preset: NVENC preset p1(fast)..p7(best quality).
        in_pix_fmt: 'bgr24' or 'yuv420p' - what the pipe is fed with.
            With 'yuv420p' the frame carries half the bytes (12 instead of
            23.7 MB at 4K) and ffmpeg's own BGR->YUV conversion on the input
            side falls away, because the encoder wants yuv420p anyway.
        """
        self.ok = False
        self.failed = False
        self._proc = None
        self.in_pix_fmt = in_pix_fmt if in_pix_fmt in ('bgr24', 'yuv420p') else 'bgr24'
        self.frame_bytes = (width * height * 3 // 2
                            if self.in_pix_fmt == 'yuv420p'
                            else width * height * 3)

        # ── Codec selection ──
        if use_nvenc:
            enc_name = 'hevc_nvenc' if codec_family == 'h265' else 'h264_nvenc'
            codec = ['-c:v', enc_name, '-preset', quality_preset,
                     '-rc', 'vbr', '-tune', 'hq',
                     '-spatial_aq', '1', '-temporal_aq', '1',
                     '-b_ref_mode', 'middle']
            # HEVC needs the explicit tag for player compatibility
            if codec_family == 'h265':
                codec += ['-tag:v', 'hvc1']
        else:
            enc_name = 'libx265' if codec_family == 'h265' else 'libx264'
            codec = ['-c:v', enc_name, '-preset', 'medium']

        # ── Rate control ──
        if mode == 'cq':
            # Quality based: CQ ~18, but with a high bitrate ceiling
            if use_nvenc:
                rate = ['-cq', '18', '-b:v', '0']
            else:
                rate = ['-crf', '18']
        else:
            b = int(mode)
            if use_nvenc:
                # VBR with a CQ target: holds the target bitrate but may rise
                # to maxrate (2x) in fast scenes -> no more macroblocking.
                # bufsize is generous to absorb peaks.
                rate = ['-cq', '19',
                        '-b:v', f'{b}M',
                        '-maxrate', f'{b*2}M',
                        '-bufsize', f'{b*3}M']
            else:
                rate = ['-b:v', f'{b}M', '-maxrate', f'{int(b*1.5)}M',
                        '-bufsize', f'{b*2}M']

        # Colour metadata for the YUV path: the frames arrive in BT.601,
        # because cv2 converts in BT.601 both ways and the reader therefore
        # hands over BT.601 (scale=out_color_matrix=bt601). So the stream is
        # TAGGED as BT.601 instead of being converted back - a tag costs
        # nothing, a second full-frame matrix pass would cost a few ms per
        # frame. Players honour the tag and show the source colours.
        tags = (['-colorspace', 'smpte170m',
                 '-color_primaries', 'bt709', '-color_trc', 'bt709']
                if self.in_pix_fmt == 'yuv420p' else [])

        cmd = ['ffmpeg', '-y',
               '-f', 'rawvideo', '-pix_fmt', self.in_pix_fmt,
               '-s', f'{width}x{height}', '-r', f'{fps}',
               '-i', '-',
               *codec, *rate, *tags,
               '-pix_fmt', 'yuv420p',        # safe player compatibility
               '-movflags', '+faststart',
               output_path]
        try:
            # stderr -> DEVNULL: this MUST be discarded, otherwise the pipe
            # deadlocks on Windows as soon as the buffer fills up.
            self._proc = subprocess.Popen(
                cmd, stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.ok = True
            _fam = 'HEVC' if codec_family == 'h265' else 'H.264'
            _hw = 'NVENC/GPU' if use_nvenc else 'CPU'
            print(f"🚀 Direct pipe encode: {_fam} {_hw} preset={quality_preset if use_nvenc else 'medium'} → {output_path}")
        except Exception as e:
            print(f"⚠️ FFmpegPipeWriter failed to start: {e}")

    def isOpened(self):
        return self.ok and not self.failed

    def write(self, frame):
        if self.failed or self._proc is None:
            return
        try:
            self._proc.stdin.write(frame.tobytes())
        except (BrokenPipeError, OSError) as e:
            self.failed = True
            print(f"❌ Pipe encode aborted: {e}")

    def release(self):
        if self._proc is None:
            return False
        try:
            self._proc.stdin.close()
        except Exception:
            pass
        try:
            rc = self._proc.wait(timeout=120)
        except subprocess.TimeoutExpired:
            self._proc.kill()
            rc = -1
        ok = (rc == 0) and not self.failed
        print(f"{'✅' if ok else '❌'} Pipe encode finished (rc={rc})")
        return ok


def deviation_flags(ft_seq, source_fps, baseline_fps, hold_ms=150.0, tolerance=0.15):
    """
    Marks frames in which the footage deviates from the baseline value.

    Definition: a frame deviates when its HOLD TIME is longer than the
    baseline allows. With baseline 60 that means anything above 16.7 ms, with
    baseline 30 anything above 33.3 ms. That way the detection also works for
    30fps footage in a 60fps container, where a doubled frame is the norm and
    not an error.

    This is based on the real per-frame frame times, NOT on the rolling FPS.
    The FPS are a one-second average and would still sit below the baseline a
    full second after a single hitch - the marker would stay lit far beyond
    the event and misrepresent its length.

    hold_ms: minimum display time. A single dropped frame lasts only
    16-33 ms and would otherwise be barely perceptible. The marker therefore
    stays up at least this long - its start time is not shifted by this.

    tolerance: safety margin against rounding. Hold times are multiples of
    the refresh interval, and 15% sits comfortably below the next step.
    """
    n = len(ft_seq)
    if n == 0:
        return []
    base = float(baseline_fps) if baseline_fps and baseline_fps > 0 else float(source_fps)
    if base <= 0:
        return [False] * n
    limit = (1000.0 / base) * (1.0 + tolerance)

    raw = [(v is not None and v > limit) for v in ft_seq]

    hold_frames = max(1, int(round((hold_ms / 1000.0) * max(source_fps, 1e-6))))
    out = [False] * n
    remaining = 0
    for i, hit in enumerate(raw):
        if hit:
            remaining = hold_frames
        if remaining > 0:
            out[i] = True
            remaining -= 1
    return out


def per_frame_frametimes(dup_flags, source_fps):
    """
    The real frame time per frame - from the duplicate flags, not from the FPS.

    BACKGROUND
    The frame time used to be computed as `1000 / eff`, where `eff` is the
    rolling one-second average of the FPS. That makes the frame time the
    reciprocal of a smoothed quantity by definition - the graph could not be
    anything other than a soft mirror image of the FPS graph.

    Digital Foundry, by contrast, shows the hold time of EVERY SINGLE frame. A
    frame followed by k duplicates was on screen for (k+1) refresh intervals:
        60fps frame (no duplicate)   -> 16.7 ms
        30fps frame (1 duplicate)    -> 33.3 ms
        20fps frame (2 duplicates)   -> 50.0 ms

    In mixed footage the value therefore jumps back and forth between those
    steps - that is the characteristic square wave.

    For comparison, a measured sequence of 20 frames at 60fps followed by
    40 frames of a 30fps pattern:
        per frame : 16.7 16.7 33.3 33.3 33.3 33.3 …   (steps)
        smoothed  : 16.7 16.7 16.7 17.5 17.4 18.2 …   (a soft ramp)
    Across the 30fps stretch the smoothed variant gives a constant 25.0 ms -
    the average, a hold time that never actually occurred.

    The value applies across the whole hold time, so the step in the graph is
    as wide as the frame really was on screen.
    """
    n = len(dup_flags)
    if n == 0:
        return []
    step = 1000.0 / max(source_fps, 1e-6)
    ft = [step] * n
    i = 0
    while i < n:
        j = i + 1
        while j < n and dup_flags[j]:
            j += 1
        hold = (j - i) * step
        for k in range(i, j):
            ft[k] = hold
        i = j
    return ft


class FFmpegFrameReader:
    """
    Delivers full BGR frames through an ffmpeg pipe with NVDEC hardware decode.

    ⚠️ NOT THE DEFAULT - in measurements on an RTX 4090 / i9-14900K this route
    was clearly SLOWER than cv2.VideoCapture:

        cv2.VideoCapture                        53.7 fps
        ffmpeg NVDEC, bgr24                     29.1 fps
        ffmpeg NVDEC, bgr24, 16 filter threads  24.4 fps

    The decode is not the problem: the same NVDEC path manages 433-480 fps in
    the pre-pass. What is expensive is everything after it - swscale converts
    NV12->BGR24 on the CPU, and the result has to go through a process pipe at
    23.7 MB per frame. cv2.VideoCapture uses the same ffmpeg libraries
    IN-PROCESS and avoids that copy entirely.

    Generalised: the ffmpeg pipe wins while the output is small (pre-pass:
    128px, 16 KB/frame -> 433 fps) and loses as soon as full frames have to be
    transported.

    Reachable via 'render_nvdec': True, in case this behaves differently on
    other hardware. The code is correct and verified:

    Frame alignment: the seek goes through `-ss <start/fps>`, exactly as in
    the pre-pass. Checked against cv2.CAP_PROP_POS_FRAMES (start frames
    0/1/7/120/301/450/599): the delivered frames are BIT-IDENTICAL.

    'render_decode_format' selects the pipe format:
      'bgr24'   - the default, bit-exact like cv2
      'yuv420p' - half the data, converted by cv2. Needs the matrix
                  adjustment out_color_matrix=bt601, because cv2 only knows
                  BT.601: without it BT.709 footage deviates by up to
                  41 levels on 26% of the pixels, with it by at most 11 on
                  0.01% of the pixels.

    Scaling is deliberately NOT done in ffmpeg: the Python side letterboxes
    through resize_with_aspect_ratio, and rebuilding that in ffmpeg would
    change the image.
    """

    MIN_BUFFER = 8
    MAX_BUFFER = 512
    RAM_FRACTION = 0.25

    def __init__(self, input_file, width, height, start_frame, n_frames,
                 source_fps, use_nvdec=True, decode_format='bgr24'):
        self.width = int(width)
        self.height = int(height)
        # 'yuv420p_raw' hands the planes through UNCONVERTED. That is the point
        # of the YUV path: the conversion to RGB used to happen here, in the
        # single reader thread, and at 4K it is the most expensive step of the
        # whole decode (~10ms/frame). Handed through raw, it moves into the
        # render workers, where it runs six times in parallel.
        self._raw_yuv = (decode_format == 'yuv420p_raw')
        if self._raw_yuv:
            decode_format = 'yuv420p'
        self._fmt = decode_format if decode_format in ('bgr24', 'yuv420p') else 'bgr24'
        if self._fmt == 'yuv420p' and (self.width % 2 or self.height % 2):
            # yuv420p needs even edge lengths
            self._fmt = 'bgr24'
            self._raw_yuv = False
        if self._fmt == 'yuv420p':
            self._frame_bytes = self.width * self.height * 3 // 2
            self._raw_shape = (self.height * 3 // 2, self.width)
        else:
            self._frame_bytes = self.width * self.height * 3
            self._raw_shape = (self.height, self.width, 3)
        self._n_frames = max(0, int(n_frames))
        self._stop = False
        self._proc = None
        self._decoder = None

        try:
            import psutil
            available_ram = psutil.virtual_memory().available
        except ImportError:
            available_ram = 8 * 1024 ** 3
        budget = int(available_ram * self.RAM_FRACTION)
        buffer_size = max(self.MIN_BUFFER,
                          min(self.MAX_BUFFER, budget // max(self._frame_bytes, 1)))

        self._queue: Queue = Queue(maxsize=buffer_size)
        self._reads = 0
        self._starved = 0
        self._fill_sum = 0
        self._fill_n = 0

        # ── Threading for the colour conversion ─────────────────────────
        # The first attempt ran with -pix_fmt bgr24 without threading and was
        # SLOWER than the cv2 path (29.1 instead of 53.7 fps) even though
        # NVDEC was active. The cause is not the decode but the swscale
        # conversion NV12->BGR24 on the CPU: it runs single-threaded and
        # writes 23.7 MB per frame. Measured in the container:
        #     bgr24 without threads    30.6 fps
        #     bgr24 -filter_threads 8  42.3 fps   (bit-exact identical)
        #     yuv420p raw              73.0 fps   (but the wrong colour matrix)
        # -filter_threads is the right lever, because the output stays
        # bit-exact (checked against the unthreaded run).
        try:
            ncpu = max(2, min(16, (os.cpu_count() or 4)))
        except Exception:
            ncpu = 4
        thread_args = ['-threads', str(ncpu), '-filter_threads', str(ncpu)]

        variants = ([('NVDEC (GPU decode)', ['-hwaccel', 'cuda'])] if use_nvdec else [])
        variants.append(('ffmpeg software', []))

        for name, hw in variants:
            cmd = ['ffmpeg', '-v', 'error', *thread_args, *hw]
            if start_frame > 0 and source_fps > 0:
                cmd += ['-ss', f'{start_frame / source_fps:.6f}']
            cmd += ['-i', input_file]
            if self._n_frames > 0:
                cmd += ['-frames:v', str(self._n_frames)]
            if self._fmt == 'yuv420p':
                # Without the matrix adjustment cv2 would read BT.709 footage
                # as BT.601 - measured up to 41 levels of deviation on 26% of
                # the pixels. With it, at most 11 on 0.01% of the pixels.
                # This applies to the raw path too: the workers convert with
                # cv2 there, which likewise only knows BT.601. The encode side
                # tags the output accordingly (see FFmpegPipeWriter).
                cmd += ['-vf', 'scale=out_color_matrix=bt601']
            cmd += ['-f', 'rawvideo', '-pix_fmt', self._fmt, '-']
            try:
                p = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                     stderr=subprocess.DEVNULL,
                                     stdin=subprocess.DEVNULL,
                                     bufsize=self._frame_bytes)
                first = self._read_exact(p.stdout, self._frame_bytes)
                if first is None:
                    raise RuntimeError('The decoder delivered no frame')
                self._proc = p
                self._first = first
                self._decoder = name
                break
            except Exception as e:
                print(f"⚠️ Render decoder '{name}' not usable ({e})")
                try:
                    p.kill()
                except Exception:
                    pass

        if self._proc is None:
            raise RuntimeError('No ffmpeg decoder available for the render pass')

        frame_mb = self._frame_bytes / 1024 ** 2
        print(f"📦 FFmpegFrameReader: {self._decoder}, "
              f"format {self._fmt}{' (raw, no conversion)' if self._raw_yuv else ''}, "
              f"{ncpu} filter threads, {buffer_size} frames buffered "
              f"({frame_mb:.0f}MB x {buffer_size} = {buffer_size*frame_mb:.0f}MB RAM)")

        self._thread = Thread(target=self._reader, daemon=True)
        self._thread.start()

    @staticmethod
    def _read_exact(pipe, n):
        # bytearray, NOT bytes: np.frombuffer on bytes returns a read-only
        # array. When source == target, resize_with_aspect_ratio passes the
        # frame through unchanged, so it goes straight into further
        # processing - and the cv2 frames of the old path were writable.
        # Keep the same behaviour.
        buf = bytearray()
        while len(buf) < n:
            chunk = pipe.read(n - len(buf))
            if not chunk:
                return None
            buf += chunk
        return buf

    def _reader(self):
        served = 0
        data = self._first
        self._first = None
        while not self._stop:
            if data is None:
                data = self._read_exact(self._proc.stdout, self._frame_bytes)
            if data is None:
                break
            frame = np.frombuffer(data, dtype=np.uint8).reshape(self._raw_shape)
            if self._fmt == 'yuv420p' and not self._raw_yuv:
                frame = cv2.cvtColor(frame, cv2.COLOR_YUV2BGR_I420)
            self._queue.put((True, frame))
            served += 1
            data = None
            if self._n_frames and served >= self._n_frames:
                break
        # Signal the end (several times, in case more than one reader waits)
        for _ in range(4):
            try:
                self._queue.put((False, None), timeout=1.0)
            except Exception:
                break

    def next_frame(self):
        self._reads += 1
        if self._queue.empty():
            self._starved += 1
        else:
            self._fill_sum += self._queue.qsize()
            self._fill_n += 1
        return self._queue.get()

    def starvation_pct(self):
        if not self._reads:
            return 0.0
        return 100.0 * self._starved / self._reads

    def get_diagnostics(self):
        if not self._reads:
            return "FFmpegFrameReader: no reads"
        avg_fill = (self._fill_sum / self._fill_n) if self._fill_n else 0.0
        cap = self._queue.maxsize
        sp = self.starvation_pct()
        if sp > 20:
            verdict = f"the DECODER is the bottleneck (despite {self._decoder})"
        elif avg_fill > cap * 0.7:
            verdict = "the RENDER WORKERS are the bottleneck"
        else:
            verdict = "decoder and workers roughly in balance"
        return (f"FFmpegFrameReader ({self._decoder}): {sp:.1f}% of frames from "
                f"an empty buffer, average fill {avg_fill:.0f}/{cap} -> {verdict}")

    def stop(self):
        self._stop = True
        try:
            self._proc.kill()
        except Exception:
            pass
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except Exception:
                break
        try:
            self._thread.join(timeout=2)
        except Exception:
            pass


class AsyncFrameReader:
    """
    Reads frames from a VideoCapture in a background thread so disk I/O
    overlaps with frame processing.  The main thread calls next_frame()
    which returns instantly if the prefetch buffer already has data.

    Buffer size is calculated dynamically based on available RAM:
      - Uses up to 25% of available RAM for the frame buffer
      - Minimum 8 frames, maximum 512 frames
      - At 4K (25MB/frame) with 32GB RAM: ~300 frames (~7.5GB)
      - At 1080p (6MB/frame) with 32GB RAM: ~512 frames (capped)
    """

    MIN_BUFFER  = 8
    MAX_BUFFER  = 512
    RAM_FRACTION = 0.25   # use up to 25% of available RAM

    def __init__(self, cap: cv2.VideoCapture):
        self._cap  = cap
        self._stop = False

        # Calculate optimal buffer size from frame dimensions + available RAM
        w   = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h   = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = cap.get(cv2.CAP_PROP_FPS) or 60
        frame_bytes = w * h * 3  # BGR uint8

        try:
            import psutil
            available_ram = psutil.virtual_memory().available
        except ImportError:
            available_ram = 8 * 1024 ** 3  # assume 8GB if psutil missing

        budget      = int(available_ram * self.RAM_FRACTION)
        buffer_size = max(self.MIN_BUFFER,
                          min(self.MAX_BUFFER, budget // max(frame_bytes, 1)))

        self._queue: Queue = Queue(maxsize=buffer_size)
        # Diagnostic counters (see next_frame/get_diagnostics)
        self._reads = 0
        self._starved = 0
        self._fill_sum = 0
        self._fill_n = 0
        self._thread = Thread(target=self._reader, daemon=True)
        self._thread.start()

        frame_mb = frame_bytes / 1024 ** 2
        total_mb = buffer_size * frame_mb
        print(f"📦 AsyncFrameReader: {buffer_size} frames buffered "
              f"({frame_mb:.0f}MB × {buffer_size} = {total_mb:.0f}MB RAM)")

    def _reader(self):
        while not self._stop:
            if self._queue.full():
                time.sleep(0.001)
                continue
            ret, frame = self._cap.read()
            self._queue.put((ret, frame))   # blocks if full, but we checked above

    def next_frame(self):
        """Return (ret, frame) — blocks only if buffer is empty (should be rare)."""
        # ── Diagnostics: does the buffer run empty? ─────────────────────
        # Decides where the bottleneck in the render pass sits:
        #   buffer regularly EMPTY -> the decoder cannot keep up. The render
        #     pass decodes with cv2.VideoCapture, i.e. in SOFTWARE and in
        #     exactly ONE thread - unlike the pre-pass, which goes through
        #     ffmpeg/NVDEC (hence 313 fps at 4K there).
        #   buffer regularly FULL  -> the render workers are the bottleneck
        #     (overlay drawing, GIL).
        self._reads += 1
        if self._queue.empty():
            self._starved += 1
        else:
            self._fill_sum += self._queue.qsize()
            self._fill_n += 1
        return self._queue.get()

    def starvation_pct(self):
        """Share of frames that were taken from an empty buffer."""
        if not self._reads:
            return 0.0
        return 100.0 * self._starved / self._reads

    def get_diagnostics(self):
        """Short report on the buffer utilisation of the render pass decoder."""
        if not self._reads:
            return "AsyncFrameReader: no reads"
        starve_pct = 100.0 * self._starved / self._reads
        avg_fill = (self._fill_sum / self._fill_n) if self._fill_n else 0.0
        cap = self._queue.maxsize
        if starve_pct > 20:
            verdict = ("the DECODER is the bottleneck - single-threaded cv2 "
                       "software decode cannot keep up")
        elif avg_fill > cap * 0.7:
            verdict = ("the RENDER WORKERS are the bottleneck - the decoder "
                       "delivers faster than they draw")
        else:
            verdict = "decoder and workers roughly in balance"
        return (f"AsyncFrameReader: {starve_pct:.1f}% of frames taken from an empty "
                f"buffer, average fill {avg_fill:.0f}/{cap} -> {verdict}")

    def stop(self):
        self._stop = True
        self._thread.join(timeout=2)
        # Drain queue so reader thread isn't blocked on a full queue
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except Exception:
                break


class AnalysisWorker(QThread):
    """Worker thread for FPS analysis with corrected sensitivity detection"""
    progress_update = pyqtSignal(int, str)
    frame_preview = pyqtSignal(np.ndarray)
    analysis_complete = pyqtSignal(bool, str)
    
    def __init__(self, input_file, output_file, settings):
        super().__init__()
        self.input_file = input_file
        self.output_file = output_file
        self.settings = settings
        self.is_cancelled = False
        self._yuv_render = False     # set in analyze_video, see _yuv_render_possible

        # Extract segment information from settings
        self.start_frame = settings.get('segment_start_frame', None)
        self.end_frame = settings.get('segment_end_frame', None)
        
        # FPS stabilization for smoother graphs
        self.fps_stabilization_buffer = collections.deque(maxlen=6)
        
        # Frame Time stabilization for smoother graphs
        self.frametime_stabilization_buffer = collections.deque(maxlen=8)
        
        # PNG Renderer instance (Singleton)
        self._png_renderer_instance = None
        
        # Frame detection (kept for UI compatibility)
        self.diff_threshold = settings.get('diff_threshold', 0.002)
        self.duplicate_count = 0
        self.total_processed = 0
        # detection_window kept for debug output compatibility
        self.detection_window = collections.deque(maxlen=60)

        # --- PairDiff Engine state ---
        # Core insight: in a 60fps capture of a 30fps game, duplicate frames
        # always have a SMALLER diff than the preceding unique frame — even
        # during camera pans, because the pan moves both frames equally.
        # So: is_duplicate = (diff[N] < diff[N-1] * PAIR_RATIO)
        # This is pan-invariant and requires no threshold calibration.
        self._prev_diff        = 0.0          # diff of previous container frame
        self._fps_window       = collections.deque(maxlen=120)  # recent unique/dup decisions
        self._diff_history_raw = collections.deque(maxlen=30)   # for min-diff floor
        
        # Debug: show whether comparison mode is active and which diff_threshold is used
        is_comparison = settings.get('comparison_mode', False)

                # ===== CUDA Accelerator initialisieren =====
        self.use_cuda = settings.get('use_cuda', False) and CUDA_ACCELERATOR_AVAILABLE and TORCH_CUDA_AVAILABLE
        self.cuda_analyzer = None
        
        if self.use_cuda:
            try:
                self.cuda_analyzer = get_cuda_analyzer(use_cuda=True)
                print(f"🚀 CUDA Acceleration ENABLED for frame analysis")
            except Exception as e:
                print(f"⚠️ Could not initialize CUDA analyzer: {e}")
                self.use_cuda = False
        else:
            print("💻 Using CPU for frame analysis")
    
    def calculate_frame_difference_simple(self, current_gray, prev_gray):
        """Raw frame difference — returns value in [0, 1]."""
        if prev_gray is None:
            return 1.0
        try:
            if self.use_cuda and self.cuda_analyzer is not None:
                return self.cuda_analyzer.calculate_frame_difference_cuda(current_gray, prev_gray)
            current_small = cv2.resize(current_gray, (128, 128), interpolation=cv2.INTER_NEAREST)
            prev_small    = cv2.resize(prev_gray,    (128, 128), interpolation=cv2.INTER_NEAREST)
            return np.mean(cv2.absdiff(current_small, prev_small)) / 255.0
        except Exception as e:
            print(f"Error calculating frame difference: {e}")
            return 1.0

    def is_frame_duplicate_corrected(self, current_gray, prev_gray):
        """
        Tile-based duplicate detection with an adaptive threshold.
        See frame_detection.py for the full description:
          - 8x8 tile comparison (robust against local motion + encoder noise)
          - adaptive threshold via largest-gap clustering (robust in dark scenes)
          - PairDiff override as a safety net
        """
        self.total_processed += 1

        if not hasattr(self, '_tile_detector') or self._tile_detector is None:
            from frame_detection import TileAdaptiveDetector
            self._tile_detector = TileAdaptiveDetector(self.diff_threshold)

        if prev_gray is None and self.total_processed <= 1:
            self._tile_detector.reset()

        is_duplicate, score = self._tile_detector.process(current_gray)

        # Update detection_window for debug output compatibility
        self.detection_window.append(not is_duplicate)

        if self.total_processed <= 5:
            print(f"🔬 Frame {self.total_processed}: score={score:.6f}, "
                  f"thr={self._tile_detector.last_threshold:.6f}, "
                  f"adaptive={self._tile_detector.adaptive_active}, "
                  f"duplicate={is_duplicate}")

        # Diagnostics every 300 frames - shows the score distribution vs. the threshold
        if self.total_processed % 300 == 0:
            print(f"🔍 DETECT [{self.total_processed}]: {self._tile_detector.get_diagnostics()}")

        if is_duplicate:
            self.duplicate_count += 1

        return is_duplicate


    def get_png_renderer(self):
        """Get or create renderer instance (Singleton). Uses CodeRenderer."""
        if self._png_renderer_instance is None:
            try:
                from code_renderer import CodeRenderer
                self._png_renderer_instance = CodeRenderer()
            except Exception as e:
                print(f"Could not create CodeRenderer: {e}")
        self._png_renderer_instance.force_cpu_blend = getattr(self, '_force_cpu_blend', False)
        return self._png_renderer_instance
    
    def _get_optimal_thread_count(self):
        """Determines the optimal number of threads for preprocessing"""
        cpu_count = multiprocessing.cpu_count()
        use_cuda = self.settings.get('use_cuda', False)

        if use_cuda:
            thread_count = min(4, max(1, cpu_count - 1))
        else:
            thread_count = min(2, max(1, cpu_count - 2))
        
        return thread_count
        
    def stabilize_fps(self, raw_fps, source_fps):
        """
        Light smoothing only — no forced snapping to target FPS values.
        The PairDiff engine already produces accurate values; we just
        smooth out single-frame noise with a short rolling average.
        """
        self.fps_stabilization_buffer.append(raw_fps)
        if len(self.fps_stabilization_buffer) < 2:
            return round(raw_fps, 1)
        avg = sum(self.fps_stabilization_buffer) / len(self.fps_stabilization_buffer)
        return round(avg, 1)
    
    def stabilize_frame_time(self, raw_frame_time):
        """Intelligent Frame Time stabilization for smoother graphs"""
        self.frametime_stabilization_buffer.append(raw_frame_time)
        
        if len(self.frametime_stabilization_buffer) < 4:
            return round(raw_frame_time, 1)
        
        avg_ft = sum(self.frametime_stabilization_buffer) / len(self.frametime_stabilization_buffer)
        
        # Common frame time targets (corresponding to common FPS)
        common_ft_targets = [16.67, 20.0, 33.33, 41.67, 50.0, 66.67]
        
        closest_target = min(common_ft_targets, key=lambda x: abs(x - avg_ft))
        
        if abs(avg_ft - closest_target) <= 0.5:
            return round(closest_target, 1)
        
        # Weighted average (more weight on recent values)
        weights = [1, 2, 3, 4]
        if len(self.frametime_stabilization_buffer) >= 4:
            recent_values = list(self.frametime_stabilization_buffer)[-4:]
            weighted_avg = sum(val * weight for val, weight in zip(recent_values, weights)) / sum(weights)
        else:
            weighted_avg = avg_ft
        
        return round(weighted_avg, 1)
    
    def set_segment_range(self, start_frame, end_frame):
        """Set segment range for analysis"""
        self.start_frame = start_frame
        self.end_frame = end_frame
        
    def cancel(self):
        """Cancel the analysis"""
        self.is_cancelled = True
    
    def ensure_truetype_fonts(self, font_settings):
        """Ensure we have TrueType fonts for PNG template renderer"""
        if font_settings and all(
            hasattr(font_settings.get(k), 'render_text') 
            for k in ['fps_font', 'framerate_font', 'frametime_font']
            if k in font_settings
        ):
            return font_settings
        
        
        for key, font in font_settings.items():
            if font:
                print(f"   • {key}: {type(font).__name__}, has render_text: {hasattr(font, 'render_text')}")
        
        needs_reinit = False
        for key in ['fps_font', 'framerate_font', 'frametime_font']:
            font = font_settings.get(key)
            if font and hasattr(font, '_initialize_fonts') and not hasattr(font, 'render_text'):
                print(f"Font {key} needs reinitialization")
                needs_reinit = True
        
        if needs_reinit:
            for key in ['fps_font', 'framerate_font', 'frametime_font']:
                font = font_settings.get(key)
                if font and hasattr(font, '_initialize_fonts'):
                    try:
                        font._initialize_fonts()
                        print(f"Reinitialized {key}")
                    except Exception as e:
                        print(f"Failed to reinitialize {key}: {e}")
        
        return font_settings
    
    def ffmpeg_prores_encode(self, input_file, output_file):
        """Encode with ProRes 422 HQ for maximum quality"""
        try:
            prores_output = output_file.replace('.mp4', '.mov')
            
            cmd = [
                'ffmpeg', '-i', input_file, '-y',
                '-c:v', 'prores_ks', '-profile:v', '2', '-vendor', 'apl0',
                '-pix_fmt', 'yuv422p10le', '-movflags', '+faststart',
                prores_output
            ]
            
            print(f"Encoding to ProRes 422 HQ: {prores_output}")
            
            result = subprocess.run(cmd, capture_output=True, timeout=600)
            
            if result.returncode == 0:
                print("ProRes encoding successful!")
                
                if output_file.endswith('.mp4'):
                    print("Creating H264 version for compatibility...")
                    h264_cmd = [
                        'ffmpeg', '-i', prores_output, '-y',
                        '-c:v', 'libx264', '-crf', '18', '-preset', 'medium',
                        '-movflags', '+faststart', output_file
                    ]
                    h264_result = subprocess.run(h264_cmd, capture_output=True)
                    
                    if h264_result.returncode == 0:
                        print(f"Created both ProRes and H264 versions")
                    else:
                        print(f"H264 creation failed")
                
                return True
            else:
                print(f"ProRes encoding failed")
                return False
                
        except Exception as e:
            print(f"FFmpeg ProRes error: {e}")
            return False

    def create_overlay(self, frame_rgb, fps_history, displayed_fps, frame_times, show_frametime, 
                    global_fps_values, global_frame_times, frametime_scale, font_settings, color_settings,
                    precomputed_stats=None, playhead_index=None, full_fps_seq=None, full_ft_seq=None,
                    full_dev_seq=None):
        """Creates the overlay using PNG template renderer"""
        
        # Ensure color settings are valid
        if not color_settings:
            color_settings = {'framerate_color': '#00FF00', 'frametime_color': '#00FF00'}
        
        # Ensure fonts are ready
        font_settings = self.ensure_truetype_fonts(font_settings)

        # COMPARISON MODE now runs through the full CodeRenderer (the layout
        # was built once before the render loop) - nothing more needed here.

        # Get necessary configurations
        layout_config = self.settings.get('layout_config')
        template_config = dict(self.settings.get('template_config') or {})
        # The stats panel needs the source frame rate for the graph scale.
        template_config.setdefault('source_fps',
                                   self.settings.get('source_fps', 60.0))
        
        # Create template_config if it is not defined
        if not template_config:
            template_config = {
                'fps_graph_template': self.settings.get('fps_graph_template'),
                'frametime_template': self.settings.get('frametime_template')
            }
        # Always merge the overlay style + line thickness from the settings,
        # so Layout Editor settings reach the renderer
        if 'overlay_style' not in template_config:
            template_config['overlay_style'] = self.settings.get('overlay_style', {})
        if 'fps_line_thickness' not in template_config:
            template_config['fps_line_thickness'] = self.settings.get('fps_line_thickness')

        # PNG Template Renderer (CodeRenderer)
        png_renderer = self.get_png_renderer()
        if png_renderer:
            try:
                return png_renderer.render_overlay(
                    frame_rgb, fps_history, displayed_fps,
                    frame_times if show_frametime else None,
                    show_frametime, layout_config, color_settings,
                    template_config, font_settings, global_fps_values, global_frame_times,
                    precomputed_stats,
                    playhead_index=playhead_index,
                    full_fps_seq=full_fps_seq,
                    full_ft_seq=full_ft_seq,
                    full_dev_seq=full_dev_seq,
                    stats_panel_config=self.settings.get('stats_panel_config')
                )
            except Exception as e:
                if not hasattr(self, '_png_error_logged'):
                    print(f"PNG template rendering failed: {e}")
                    import traceback
                    traceback.print_exc()
                    self._png_error_logged = True

        # Minimal Fallback
        overlay = frame_rgb.copy()
        try:
            # Base FPS display
            text = f"FPS: {displayed_fps:.1f}" if displayed_fps >= 0 else "FPS: ---"
            font = cv2.FONT_HERSHEY_SIMPLEX
            font_scale = 2.0
            thickness = 3
            
            # Position
            (text_width, text_height), _ = cv2.getTextSize(text, font, font_scale, thickness)
            x, y = 50, 80
            
            # Black background for better legibility
            cv2.rectangle(overlay, (x-10, y-text_height-10), (x+text_width+10, y+10), (0, 0, 0), -1)
            
            # Text with an outline
            cv2.putText(overlay, text, (x, y), font, font_scale, (0, 0, 0), thickness+2, cv2.LINE_AA)
            cv2.putText(overlay, text, (x, y), font, font_scale, (0, 255, 0), thickness, cv2.LINE_AA)
            
            # Note that minimal mode is active
            info_text = "Minimal Mode (Check templates folder)"
            cv2.putText(overlay, info_text, (x, y+50), font, 0.7, (255, 255, 0), 2, cv2.LINE_AA)
            
            return overlay
        except Exception as e:
            print(f"Even minimal rendering failed: {e}")
            return frame_rgb
    
    def run(self):
        """Main analysis function running in separate thread"""
        try:
            self.analyze_video()
        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            print(f"ANALYSIS ERROR: {error_details}")
            self.analysis_complete.emit(False, f"Analysis failed: {str(e)}")
    
    def _stats_warmup_frames(self, source_fps):
        """
        Number of frames at the start of the segment that do NOT enter MIN/MAX/AVG.

        Reason: the rolling 1s window of the FPS computation is not yet full at
        the start, and the adaptive detector needs history (MIN_HISTORY = 20
        frames) before it works sensibly. Values from that phase are
        systematically too low and would distort MIN and AVG.

        Default 2.0s (configurable via 'stats_warmup_seconds').
        """
        warm_s = float(self.settings.get('stats_warmup_seconds', 2.0))
        return int(round(max(0.0, warm_s) * source_fps))

    @staticmethod
    def _stats_valid_mask(fps_seq, ft_seq, source_fps, warm_n):
        """
        Returns the indices that enter MIN/MAX/AVG - IDENTICAL for FPS and
        frame time.

        This is the core of the fix: both statistics used to have filters of
        their own (fps: 1.0 < v <= source_fps*1.05, ft: 0.5 < v < 2000.0).
        A frame with eff=0 yields ft=1000.0 by definition (the sentinel from
        `ft = 1000.0/eff if eff > 0 else 1000.0`). The FPS filter threw it
        out, the FT filter let it through -> the frame time statistics
        contained frames the FPS statistics knew nothing about. Visible
        consequence: a MAX frame time of exactly 1000.0ms and an AVG that did
        not match the AVG of the FPS (log: FPS avg=57.27 -> should be ~17.5ms,
        displayed 22.76ms).

        Now the FPS value alone decides validity; the frame time follows the
        same frame set.
        """
        idx = []
        n = min(len(fps_seq), len(ft_seq))
        for i in range(warm_n, n):
            v = fps_seq[i]
            if v is None or not (1.0 < v <= source_fps * 1.05):
                continue
            t = ft_seq[i]
            if t is None or not (0.5 < t < 2000.0):
                continue
            idx.append(i)
        return idx

    def _compute_final_stats(self, fps_seq, ft_seq, source_fps):
        """Final MIN/MAX/AVG for FPS and frame time."""
        warm_n = self._stats_warmup_frames(source_fps)
        idx = self._stats_valid_mask(fps_seq, ft_seq, source_fps, warm_n)
        if not idx:
            empty = {'avg': -1, 'min': -1, 'max': -1}
            return dict(empty), dict(empty)
        f = [fps_seq[i] for i in idx]

        # ── Frame time sample ───────────────────────────────────────────
        # In 'per_frame' mode every source frame carries the value of the hold
        # time it belongs to. For the GRAPH that is right - the step has to be
        # as wide as the frame really was on screen. For the AVERAGE it would
        # be wrong: long hold times would be counted several times and pull
        # the value up (computed on a clip with 21% duplicates: 25.89 ms
        # instead of the correct 21.10 ms).
        # What is right is one value per ACTUALLY PRESENTED frame, i.e. only
        # at the start of each run. Check: total time / number of presented
        # frames = 1779 x 16.667 / 1405 = 21.10 ms - which matches the
        # reciprocal of the mean FPS.
        flags = getattr(self, '_full_dup_flags', None)
        per_frame_mode = (self.settings.get('frametime_mode', 'per_frame')
                          == 'per_frame')
        if per_frame_mode and flags and len(flags) >= len(ft_seq):
            ft_idx = [i for i in idx if not flags[i]]
        else:
            ft_idx = idx
        if not ft_idx:
            ft_idx = idx
        t = [ft_seq[i] for i in ft_idx]

        print(f"📊 Statistics basis: {len(idx)} of {len(fps_seq)} frames "
              f"(warmup {warm_n} frames = {warm_n/max(source_fps,1):.1f}s excluded)"
              + (f", frame time across {len(ft_idx)} presented frames"
                 if len(ft_idx) != len(idx) else ""))
        return ({'avg': sum(f)/len(f), 'min': min(f), 'max': max(f)},
                {'avg': sum(t)/len(t), 'min': min(t), 'max': max(t)})

    def _precompute_display_stats(self, source_fps, fps_update_interval):
        """
        Precompute the displayed FPS + the running min/max/avg per frame.
        Makes the render pass stateless -> parallelisable.
        Replicates the sequential logic exactly (update interval, warmup, fade
        gaps holding the last value).
        """
        seq, fts = self._full_fps_seq, self._full_ft_seq
        n = len(seq)
        disp = [-1] * n
        pf, pt = [None] * n, [None] * n
        win = collections.deque(maxlen=30)
        cnt = 0
        shown = int(round(source_fps))
        last = float(source_fps)
        fa = {'sum': 0.0, 'n': 0, 'min': None, 'max': None}
        ta = {'sum': 0.0, 'n': 0, 'min': None, 'max': None}
        warm = self._stats_warmup_frames(source_fps)
        _flags = getattr(self, '_full_dup_flags', None)
        _per_frame = (self.settings.get('frametime_mode', 'per_frame') == 'per_frame'
                      and _flags is not None and len(_flags) >= n)
        for i in range(n):
            sv = seq[i]
            eff = sv if sv is not None else last
            last = eff
            win.append(eff)
            cnt += 1
            if cnt >= fps_update_interval:
                if win:
                    shown = round(sum(win) / len(win))
                cnt = 0
            disp[i] = -1 if i <= 60 else shown
            if i >= warm:
                # FPS decides validity and the frame time follows the same
                # frame - otherwise the FT statistics would contain the 1000ms
                # sentinel from 0 fps frames, which the FPS statistics reject.
                tv = fts[i] if i < len(fts) else None
                valid = (sv is not None and 1.0 < sv <= source_fps * 1.05
                         and tv is not None and 0.5 < tv < 2000.0)
                if valid:
                    fa['sum'] += sv; fa['n'] += 1
                    fa['min'] = sv if fa['min'] is None else min(fa['min'], sv)
                    fa['max'] = sv if fa['max'] is None else max(fa['max'], sv)
                    # Count the frame time only at presented frames, otherwise
                    # long hold times would be counted several times (see
                    # _compute_final_stats).
                    if not (_per_frame and _flags[i]):
                        ta['sum'] += tv; ta['n'] += 1
                        ta['min'] = tv if ta['min'] is None else min(ta['min'], tv)
                        ta['max'] = tv if ta['max'] is None else max(ta['max'], tv)
            # Show NO statistics during the warmup phase. There used to be a
            # fallback to self._final_*_stats here - which meant the overlay
            # already showed the final values of the whole segment from frame
            # 0, i.e. numbers that could not possibly have been measured at
            # that point. None is deliberately left out by the renderer
            # (_draw_stats bails out on missing data).
            pf[i] = ({'avg': fa['sum']/fa['n'], 'min': fa['min'], 'max': fa['max']}
                     if fa['n'] else None)
            pt[i] = ({'avg': ta['sum']/ta['n'], 'min': ta['min'], 'max': ta['max']}
                     if ta['n'] else None)
        return disp, pf, pt

    def _yuv_render_possible(self, src_w, src_h, dst_w, dst_h):
        """
        Decides whether the render pass can run in YUV.

        What it buys: the reader hands over raw I420 instead of converting to
        BGR itself. That conversion is the most expensive single step of the
        decode at 4K (~10ms per frame) and used to run in the ONE reader
        thread, which is exactly why the render pass sat at 53.7 fps with 97.8%
        buffer starvation. In the workers the same conversion runs six times
        in parallel, and the encoder pipe carries half the bytes on top
        (12 instead of 23.7 MB per frame at 4K).

        Measured decoder throughput at 4K (RTX 4090 / i9-14900K):
            cv2.VideoCapture (converts to BGR itself)   53.7 fps
            ffmpeg pipe, bgr24                          30.6 fps
            ffmpeg pipe, bgr24, 8 filter threads        42.3 fps
            ffmpeg pipe, yuv420p raw                    73.0 fps

        Conditions, all of them necessary:
          - 'render_yuv' switched on
          - the parallel render pass (the conversion has to be parallel, or
            nothing is gained)
          - source resolution == target resolution. Scaling would have to
            happen in RGB after the conversion, and a scaled frame would need
            a full conversion back, which removes the point.
          - even edge lengths (4:2:0) and no comparison mode (it crops).
        """
        if not self.settings.get('render_yuv', False):
            return False
        reasons = []
        if not (self.settings.get('parallel_render', True)
                and int(self.settings.get('render_workers', 6)) >= 2):
            reasons.append('the parallel render pass is switched off')
        if (src_w, src_h) != (dst_w, dst_h):
            reasons.append(f'resolution changes ({src_w}x{src_h} -> {dst_w}x{dst_h})')
        if dst_w % 2 or dst_h % 2:
            reasons.append('odd edge length')
        if self.settings.get('comparison_mode', False):
            reasons.append('comparison mode crops the frames')
        if self.target_bitrate_final == 'prores':
            reasons.append('ProRes runs through the legacy writer')
        if reasons:
            print(f"🎨 YUV render path not used: {', '.join(reasons)} "
                  f"-> standard BGR path")
            return False
        return True

    def _run_render_parallel(self, frame_reader, out, actual_start, actual_end,
                             source_fps, target_width, target_height,
                             fps_update_interval, segment_frames):
        """
        Parallel render pass: N worker threads render overlays, and one
        reorder encoder writes the frames into the NVENC pipe in strict order.
        Possible because the pre-pass makes the render pass stateless (every
        frame depends only on its index).
        """
        import threading as _th
        import traceback as _tb
        workers = max(2, min(12, int(self.settings.get('render_workers', 6))))
        print(f"⚡ Parallel rendering: {workers} worker threads")

        # Do not share GPU blends across threads -> CPU blend (numpy, GIL-free)
        self._force_cpu_blend = True

        disp, pf, pt = self._precompute_display_stats(source_fps, fps_update_interval)
        seq, ftseq = self._full_fps_seq, self._full_ft_seq
        flags = getattr(self, '_full_dup_flags', [])
        n_total = min(len(seq), actual_end - actual_start) if seq else (actual_end - actual_start)

        show_frametime = self.settings.get('show_frametime', True)
        frametime_scale = self.settings.get('frametime_scale', {
            'min': 16.7, 'mid': 33.3, 'max': 50.0,
            'labels': ['16.7', '33.3', '50.0']
        })
        font_settings = self.settings.get('font_settings', {})
        color_settings = self.settings.get('color_settings', {
            'framerate_color': '#00FF00',
            'frametime_color': '#00FF00'
        })
        comparison_mode = self.settings.get('comparison_mode', False)
        _dummy_hist = [float(source_fps)] * 2
        _dummy_ft = [1000.0 / max(1.0, float(source_fps))] * 2

        task_q = Queue(maxsize=workers * 2)
        done_q = Queue(maxsize=workers * 4)
        t_start = time.perf_counter()

        # ── Stage timing (accumulated thread-safely) ────────────────────
        # Answers: does the time go into scaling, into the colour conversion
        # or into drawing the overlay? These are sums across ALL workers, so
        # the total is larger than the wall-clock time - what matters is the
        # ratio between the items.
        _stage = {'resize': 0.0, 'cvt_in': 0.0, 'overlay': 0.0, 'cvt_out': 0.0}
        _stage_lock = Lock()

        # YUV path: the reader hands over raw I420, the workers convert to RGB
        # and back, and the encoder pipe takes yuv420p directly. Decided by
        # the reader, which is the only place that knows what it delivers.
        yuv_mode = bool(getattr(frame_reader, '_raw_yuv', False))
        if yuv_mode:
            print("🎨 YUV render path active: conversion in the workers, "
                  "yuv420p straight into the encoder")

        def _render_one(idx, frame):
            _t = time.perf_counter()
            if yuv_mode:
                # The frame arrives as raw I420 (height*3/2, width) and needs
                # no scaling - the YUV path only runs when source and target
                # resolution match (see _yuv_render_possible).
                _t_resize = _t
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_YUV2RGB_I420)
            elif comparison_mode:
                fp = adaptive_crop_and_resize(frame, target_width, target_height,
                                              comparison_mode=True)
                _t_resize = time.perf_counter()
                frame_rgb = cv2.cvtColor(fp, cv2.COLOR_BGR2RGB)
            else:
                fp = resize_with_aspect_ratio(frame, target_width, target_height)
                _t_resize = time.perf_counter()
                frame_rgb = cv2.cvtColor(fp, cv2.COLOR_BGR2RGB)
            _t_cvt_in = time.perf_counter()
            stats = ({'fps': pf[idx], 'frametime': pt[idx]}
                     if idx < len(pf) else None)
            fw = self.create_overlay(
                frame_rgb, _dummy_hist,
                disp[idx] if idx < len(disp) else -1,
                _dummy_ft, show_frametime,
                [], [], frametime_scale,
                font_settings, color_settings, stats,
                playhead_index=idx,
                full_fps_seq=seq, full_ft_seq=ftseq,
                full_dev_seq=getattr(self, '_full_dev_flags', None))
            _t_overlay = time.perf_counter()
            if yuv_mode:
                out_bgr = cv2.cvtColor(fw, cv2.COLOR_RGB2YUV_I420)
            else:
                out_bgr = cv2.cvtColor(fw, cv2.COLOR_RGB2BGR)
            _t_end = time.perf_counter()
            with _stage_lock:
                _stage['resize']  += _t_resize  - _t
                _stage['cvt_in']  += _t_cvt_in  - _t_resize
                _stage['overlay'] += _t_overlay - _t_cvt_in
                _stage['cvt_out'] += _t_end     - _t_overlay
            return out_bgr

        def _worker():
            while True:
                item = task_q.get()
                if item is None:
                    break
                w_idx, fr = item
                try:
                    fb = _render_one(w_idx, fr)
                except Exception as e:
                    _tb.print_exc()
                    print(f"⚠️ Render worker error @frame {w_idx}: {e} - frame without overlay")
                    try:
                        # In YUV mode the frame already has the output format,
                        # so it goes through unchanged - just without overlay.
                        fb = (fr if yuv_mode else
                              resize_with_aspect_ratio(fr, target_width, target_height))
                    except Exception:
                        fb = (np.zeros((target_height * 3 // 2, target_width), dtype=np.uint8)
                              if yuv_mode else
                              np.zeros((target_height, target_width, 3), dtype=np.uint8))
                done_q.put((w_idx, fb))

        enc = {'written': 0}
        disp_state = {'n': 0, 'done': False}

        def _encoder():
            pending = {}
            nxt = 0
            while True:
                if nxt in pending:
                    fb = pending.pop(nxt)
                else:
                    try:
                        item = done_q.get(timeout=0.25)
                    except Exception:
                        if disp_state['done'] and enc['written'] >= disp_state['n']:
                            break
                        continue
                    i2, fb2 = item
                    if i2 != nxt:
                        pending[i2] = fb2
                        continue
                    fb = fb2
                out.write(fb)
                self.frames_encoded += 1
                enc['written'] += 1
                w = enc['written']
                nxt += 1
                if w % 30 == 0:
                    prog = 15 + int((w / max(1, segment_frames)) * 70)
                    # Fade-excluded frames are None. They used to be logged
                    # here as "FPS: 0.0", which made them look like a real
                    # 0 fps drop - while in the overlay the graph correctly
                    # holds the last value at that point.
                    _sv = seq[w-1] if (w-1) < len(seq) else None
                    _fps_txt = "FPS: --- (Fade)" if _sv is None else f"FPS: {_sv:.1f}"
                    dr = (self.duplicate_count / self.total_processed * 100)                          if self.total_processed else 0
                    self.progress_update.emit(
                        prog, f"Frame {actual_start + w}/{actual_end} - "
                              f"{_fps_txt} - Duplicates: {dr:.1f}%")
                if w % 50 == 0:
                    # The preview expects BGR; in YUV mode it is converted
                    # here, for every 50th frame only.
                    self.frame_preview.emit(
                        cv2.cvtColor(fb, cv2.COLOR_YUV2BGR_I420) if yuv_mode else fb)
                if w % 100 == 0:
                    dt = time.perf_counter() - t_start
                    print(f"⚡ PARALLEL: {w} frames in {dt:.1f}s -> "
                          f"{w/dt:.1f} FPS ({dt/w*1000:.1f}ms/frame, {workers} workers)")
                if disp_state['done'] and w >= disp_state['n']:
                    break

        enc_t = _th.Thread(target=_encoder, daemon=True)
        enc_t.start()

        # Render frame 0 SYNCHRONOUSLY once -> the bg/border/font caches are
        # built by the main thread before the workers start in parallel.
        ret, first = frame_reader.next_frame()
        if not ret:
            disp_state['done'] = True
            enc_t.join()
            return 0
        fb0 = _render_one(0, first)
        done_q.put((0, fb0))
        self.total_processed += 1
        if flags and len(flags) > 0 and flags[0]:
            self.duplicate_count += 1

        threads = [_th.Thread(target=_worker, daemon=True) for _ in range(workers)]
        for t in threads:
            t.start()

        idx = 1
        while idx < n_total:
            if self.is_cancelled:
                break
            ret, frame = frame_reader.next_frame()
            if not ret:
                break
            task_q.put((idx, frame))
            self.total_processed += 1
            if idx < len(flags) and flags[idx]:
                self.duplicate_count += 1
            idx += 1

        disp_state['n'] = idx
        disp_state['done'] = True
        for _ in threads:
            task_q.put(None)
        for t in threads:
            t.join()
        enc_t.join()

        dt = time.perf_counter() - t_start
        if idx:
            print(f"⚡ PARALLEL finished: {idx} frames in {dt:.1f}s "
                  f"({idx/max(dt, 1e-6):.1f} FPS, {dt/idx*1000:.1f}ms/Frame)")
            # ── Where does the time go? ─────────────────────────────────
            _tot = sum(_stage.values()) or 1e-9
            print(f"⏲️  Render pass breakdown (summed across {workers} workers, "
                  f"{_tot:.1f}s of worker time for {dt:.1f}s wall clock):")
            for _k, _label in (('resize',  'Scaling/cropping'),
                               ('cvt_in',  'Colour conversion BGR->RGB'),
                               ('overlay', 'Drawing the overlay'),
                               ('cvt_out', 'Colour conversion RGB->BGR')):
                _v = _stage[_k]
                print(f"     {_label:28s} {_v*1000/idx:7.2f} ms/Frame  "
                      f"({100*_v/_tot:5.1f}%)")
            _par = _tot / max(dt, 1e-9)
            # Low parallelism does NOT automatically mean the GIL. When the
            # decoder starves the workers they inevitably run serially - in
            # the 4K run of 30 July this line reported "GIL limited" at 97.8%
            # buffer starvation, which would have named the wrong cause.
            try:
                _starve = frame_reader.starvation_pct()
            except Exception:
                _starve = 0.0
            if _par >= workers * 0.6:
                _verdict = "scales well"
            elif _starve > 25:
                _verdict = (f"not the GIL - workers waiting on the decoder "
                            f"({_starve:.0f}% Leerlauf)")
            else:
                _verdict = "GIL limited"
            print(f"     Effective parallelism: {_par:.2f}x of {workers} workers "
                  f"({_verdict})")
            if _starve > 25 and _tot > 0:
                _ceiling = idx / max(_tot / workers, 1e-9)
                print(f"     Computed ceiling without the decode limit: "
                      f"~{_ceiling:.0f} fps (aktuell {idx/max(dt,1e-9):.1f} fps)")
            try:
                print(f"     {frame_reader.get_diagnostics()}")
            except Exception:
                pass
            try:
                _summary = self.get_png_renderer().get_stage_summary()
                if _summary:
                    print(_summary)
            except Exception:
                pass
        return idx

    def _iter_prepass_gray(self, cap, actual_start, actual_end, source_fps,
                           preroll=0):
        """
        Delivers 128x128 greyscale frames for the pre-pass - as fast as possible.
        Decode chain: NVDEC (GPU) -> ffmpeg software -> cv2 fallback.

        The core trick: the pre-pass NEVER needs the full image (the detector
        and fade detection work on 128px). ffmpeg decodes, downscales and
        converts by itself and pipes only 16KB/frame instead of ~24MB (4K
        BGR) into Python - so the pre-pass is no longer decode limited.

        preroll: the number of frames BEFORE actual_start that are prepended.
        They only serve to warm up the detector and the window, and the caller
        discards them (see _prepass_collect_fps). The caller must make sure
        that preroll <= actual_start.
        """
        preroll = max(0, min(int(preroll), int(actual_start)))
        decode_start = actual_start - preroll
        n_frames = max(0, actual_end - actual_start) + preroll
        fb = 128 * 128

        def _read_exact(pipe, n):
            buf = b''
            while len(buf) < n:
                chunk = pipe.read(n - len(buf))
                if not chunk:
                    return None
                buf += chunk
            return buf

        variants = [
            ('NVDEC (GPU-Decode)', ['-hwaccel', 'cuda']),
            ('ffmpeg-Software', []),
        ]
        proc = None
        first = None
        name_used = None
        for name, hw in variants:
            p = None
            try:
                cmd = ['ffmpeg', '-v', 'error', *hw]
                if decode_start > 0 and source_fps > 0:
                    cmd += ['-ss', f'{decode_start / source_fps:.6f}']
                cmd += ['-i', self.input_file,
                        '-frames:v', str(n_frames),
                        '-vf', 'scale=128:128:flags=neighbor,format=gray',
                        '-f', 'rawvideo', '-']
                p = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                     stderr=subprocess.DEVNULL,
                                     stdin=subprocess.DEVNULL)
                f0 = _read_exact(p.stdout, fb)
                if f0 is None:
                    raise RuntimeError('The decoder delivered no frame')
                proc, first, name_used = p, f0, name
                break
            except Exception as e:
                print(f"⚠️ Pre-pass decoder '{name}' not usable - next fallback ({e})")
                if p is not None:
                    try:
                        p.kill()
                    except Exception:
                        pass

        if proc is not None:
            try:
                self._prepass_decoder = name_used
                print(f"⚡ Pre-pass decoder: {name_used} (128px grey pipe)")
                yield np.frombuffer(first, dtype=np.uint8).reshape(128, 128)
                served = 1
                while served < n_frames and not self.is_cancelled:
                    data = _read_exact(proc.stdout, fb)
                    if data is None:
                        break
                    yield np.frombuffer(data, dtype=np.uint8).reshape(128, 128)
                    served += 1
                return
            finally:
                try:
                    proc.kill()
                except Exception:
                    pass

        # cv2 fallback: the old route (full decode + shrink in Python)
        self._prepass_decoder = 'cv2 fallback'
        print("🐢 Pre-pass decoder: cv2 fallback (full frame decode)")
        cap.set(cv2.CAP_PROP_POS_FRAMES, decode_start)
        served = 0
        while served < n_frames:
            if self.is_cancelled:
                break
            ret, frame = cap.read()
            if not ret:
                break
            small = cv2.resize(frame, (128, 128), interpolation=cv2.INTER_NEAREST)
            yield cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
            served += 1

    def _prepass_collect_fps(self, cap, actual_start, actual_end, source_fps):
        """
        Pass 1: collects the FPS/FT values per frame WITHOUT rendering.
        Needed for the DF playhead graph (the render pass needs the future).
        Returns (fps_seq, ft_seq, fade_excluded_set).
        Uses exactly the same detection and window logic as the render pass.
        """
        import collections as _c
        detection_window = _c.deque(maxlen=int(source_fps))
        fps_seq, ft_seq = [], []
        dup_flags = []
        prev_gray = None
        last_eff = source_fps

        # Its own detector state (separate from the render pass)
        self._tile_detector = None
        self.total_processed = 0
        self.duplicate_count = 0

        fade_det = None
        if getattr(self, '_fade_enabled', False):
            from fade_detection import FadeDetector
            fade_det = FadeDetector(
                source_fps,
                std_threshold=float(self.settings.get('fade_std_threshold', 8.0)),
                buffer_seconds=float(self.settings.get('fade_buffer_ms', 2000)) / 1000.0,
            )
            print(f"🎬 Fade pre-pass ACTIVE (std<{fade_det.std_threshold}, "
                  f"buffer {fade_det.buffer_frames} frames, min {fade_det.min_fade_frames} frames)")
        else:
            print(f"⚪ Fade detection DISABLED (checkbox in Options not set)")

        _t_pre = time.perf_counter()
        n_expected = max(0, actual_end - actual_start)

        # ── PRE-ROLL ────────────────────────────────────────────────────
        # Without a run-up the detector starts "cold" on every segment: the
        # first MIN_HISTORY (20) frames still run with the user fallback
        # threshold, because the adaptive / low-motion branch only kicks in
        # once there is enough history. In calm footage (scores ~0.002 against
        # a fallback of 0.005) those 20 frames are therefore all counted as
        # duplicates. The rolling 1s window then carries the error another
        # 60 frames - measured in the 4K run of 30 July:
        #   index 30 -> 22 fps (computed: (10/30)*60 = 20)
        #   index 60 -> 41 fps (computed: (40/60)*60 = 40)
        #   index 90 -> 60 fps (the wrong duplicates have left the window)
        # The statistics warmup exclusion only hides this in MIN/MAX/AVG; in
        # the rendered graph the ramp stayed visible.
        #
        # Solution: decode frames BEFORE the segment start as well, so the
        # detector history and the window are already full at segment index 0.
        # Size = window length (source_fps) + MIN_HISTORY, so that at index 0
        # the window holds nothing but frames the detector already classified
        # with a warm history.
        _preroll_want = int(source_fps) + 20
        preroll = max(0, min(_preroll_want, int(actual_start)))
        if preroll < _preroll_want:
            # The segment starts at (or close to) the start of the video -
            # there simply are no frames before it. The warmup effect then
            # remains; the statistics still absorb it via stats_warmup_seconds.
            print(f"⚠️ Pre-roll only {preroll} instead of {_preroll_want} frames possible "
                  f"(the segment starts at frame {actual_start}) - "
                  f"some settling at the segment start stays visible")
        elif preroll:
            print(f"🔥 Pre-roll: {preroll} frames before the segment start, to warm up "
                  f"(detector history + 1s window); they are discarded")

        idx = actual_start
        _fade_frame_count = 0
        _min_std_seen = 999.0
        _seen = 0          # counts ALL delivered frames including the pre-roll
        for gray in self._iter_prepass_gray(cap, actual_start, actual_end,
                                            source_fps, preroll=preroll):
            if self.is_cancelled:
                break

            _seen += 1
            _in_preroll = _seen <= preroll

            is_dup = self.is_frame_duplicate_corrected(gray, prev_gray)
            prev_gray = gray
            detection_window.append(not is_dup)

            if _in_preroll:
                # The detector and the window are fed now - but this frame
                # does not belong to the segment and must not appear in ANY
                # result (neither the sequences nor the duplicate statistics
                # nor the fade detection, whose indices would otherwise shift).
                if _seen == preroll:
                    self.total_processed = 0
                    self.duplicate_count = 0
                continue

            dup_flags.append(bool(is_dup))

            ws = len(detection_window)
            if ws >= 4:
                eff = (sum(detection_window) / ws) * source_fps
                eff = max(0.0, min(eff, source_fps))
            else:
                eff = last_eff
            last_eff = eff
            ft = 1000.0 / eff if eff > 0 else 1000.0

            fps_seq.append(eff)
            ft_seq.append(ft)

            if fade_det is not None:
                _is_f = fade_det.process(gray)
                if _is_f:
                    _fade_frame_count += 1
                # Diagnostics: track the smallest std value
                _s = float(gray.std())
                if _s < _min_std_seen:
                    _min_std_seen = _s

            idx += 1
            if idx % 300 == 0:
                pct = int((idx - actual_start) / max(1, actual_end - actual_start) * 12)
                self.progress_update.emit(2 + pct, f"Pre-analysis {idx-actual_start}/{actual_end-actual_start}")

        # Decoder frame-count reconciliation: when ffmpeg delivers marginally
        # fewer frames than expected, pad with the last value (keeps the
        # playhead aligned with the cv2-based render pass).
        _got = len(fps_seq)
        if not self.is_cancelled and 0 < _got < n_expected:
            _pad = n_expected - _got
            if _pad > 5:
                print(f"⚠️ Pre-pass: the decoder delivered {_got}/{n_expected} frames - padding {_pad}")
            fps_seq.extend([fps_seq[-1]] * _pad)
            ft_seq.extend([ft_seq[-1]] * _pad)
            dup_flags.extend([False] * _pad)
        _dt_pre = time.perf_counter() - _t_pre
        if _got:
            print(f"⏱️ Pre-pass: {_got} frames in {_dt_pre:.1f}s "
                  f"({_got/max(_dt_pre, 1e-6):.0f} FPS, Decoder: {getattr(self, '_prepass_decoder', '?')})")

        if fade_det is not None:
            print(f"🔍 FADE DIAG: {_fade_frame_count} uniform frames detected, "
                  f"lowest std={_min_std_seen:.2f} (threshold={fade_det.std_threshold})")

        fade_excluded = fade_det.finalize_excluded() if fade_det is not None else set()
        if fade_det is not None:
            print(f"🎬 Fade pre-pass: {len(fade_det.fade_blocks())} fade(s), "
                  f"{len(fade_excluded)} frames excluded")

        # Reset the detector for the render pass
        self._tile_detector = None
        self.total_processed = 0
        self.duplicate_count = 0
        self._full_dup_flags = dup_flags
        return fps_seq, ft_seq, fade_excluded

    def analyze_video(self):
        """Analyze video with corrected frame detection and WORKING frame time calculation"""
        
        try:
            # Open video
            cap = cv2.VideoCapture(self.input_file)
            if not cap.isOpened():
                raise ValueError("Could not open input video")
            
            # Get video properties
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            source_fps = cap.get(cv2.CAP_PROP_FPS)
            source_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            source_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            
            # Debug info
            sensitivity_names = {
                0.0005: "Very High", 0.001: "High", 0.002: "Medium", 
                0.005: "Low", 0.01: "Very Low"
            }
            current_sensitivity = sensitivity_names.get(self.diff_threshold, f"Custom ({self.diff_threshold})")
            self.progress_update.emit(2, f"Sensitivity: {current_sensitivity}")
            
            # Get baseline FPS
            baseline_fps = self.settings.get('baseline_fps', 0)
            if baseline_fps > 0:
                initial_fps = float(baseline_fps)
                initial_frame_time = 1000.0 / initial_fps
                self.progress_update.emit(5, f"Baseline: {baseline_fps} FPS")
            else:
                initial_fps = source_fps
                initial_frame_time = 1000.0 / source_fps if source_fps > 0 else 33.33
        
            # Handle segments
            if self.settings.get('comparison_mode', False):
                actual_start = 0
                actual_end = total_frames
            else:
                actual_start = self.start_frame or 0
                actual_end = self.end_frame or total_frames
                actual_start = max(0, actual_start)
                actual_end = min(total_frames, actual_end)
                if actual_start >= actual_end:
                    raise ValueError("Invalid segment: start >= end")

            segment_frames = actual_end - actual_start
            
            # Get resolution settings
            if self.settings.get('comparison_mode', False):
                target_width, target_height = self.settings.get('comparison_resolution', (960, 1080))
            else:
                target_width, target_height = self.settings.get('resolution', (1920, 1080))

            # Build the comparison layout once up front (thread-safe, before
            # the possibly parallel render loop). Graph 1750x400 @ 4K, FPS
            # number higher up and smaller. Uses the full CodeRenderer ->
            # colours / frosted glass / style.
            if self.settings.get('comparison_mode', False):
                fw, fh = target_width, target_height
                # Normalise to the HEIGHT (4K = 2160p) so that 1750x400 holds
                # literally at 4K - the comparison frames are only half as
                # wide but just as tall as the original footage.
                s = fh / 2160.0
                gw = min(int(1750 * s), fw - int(120 * s))   # no wider than the frame
                gh = int(400 * s)
                gx = int(60 * s);   gy = fh - gh - int(80 * s)
                # FPS number top left, 50px (4K scaled) from each edge
                fps_x = int(50 * s)
                fps_y = int(50 * s)
                self.settings['layout_config'] = {
                    'fps_display': {
                        'x': fps_x, 'y': fps_y, 'visible': True,
                        'font_scale_multiplier': 0.85,
                    },
                    'frame_rate_graph': {
                        'x': gx, 'y': gy, 'width': gw, 'height': gh, 'visible': True,
                    },
                    'frame_time_graph': {'x': gx, 'y': gy, 'width': gw, 'height': gh, 'visible': False},
                    'fps_statistics': {'x': gx, 'y': gy, 'visible': False},
                    'frametime_statistics': {'x': gx, 'y': gy, 'visible': False},
                }
                # Title ("FRAME RATE") + axis labels slightly larger in comparison mode
                _os = dict(self.settings.get('overlay_style') or {})
                _os['text_boost'] = 1.25
                self.settings['overlay_style'] = _os
                if isinstance(self.settings.get('template_config'), dict):
                    self.settings['template_config']['overlay_style'] = _os

            # Setup video writer
            temp_output = self.output_file.replace('.mp4', '_temp.avi')
            self.temp_output = temp_output
            self.final_output = self.output_file
            self.target_bitrate_final = self.settings.get('bitrate', 60)

            # ── Direct pipe encode (NVENC/x264) instead of an intermediate MJPEG file ──
            # Saves the intermediate encode + the re-encode pass. ProRes stays legacy.
            self._pipe_direct = False
            out = None

            # ── YUV render path ('render_yuv') ──────────────────────────────
            # Decided here, because the writer is created before the reader and
            # both sides have to agree on the format.
            self._yuv_render = self._yuv_render_possible(
                source_width, source_height, target_width, target_height)
            _in_fmt = 'yuv420p' if self._yuv_render else 'bgr24'

            if self.target_bitrate_final != 'prores':
                _mode = 'cq' if self.target_bitrate_final == 'opencv' else int(self.target_bitrate_final)
                # Codec + preset from the settings (default: HEVC, p6 = high quality)
                _codec_family = self.settings.get('codec_family', 'h265')
                _preset = self.settings.get('nvenc_preset', 'p6')
                _nv = _probe_nvenc(_codec_family)
                # HEVC not available? -> fall back to H.264 NVENC
                if not _nv and _codec_family == 'h265':
                    if _probe_nvenc('h264'):
                        _codec_family = 'h264'
                        _nv = True
                pw = FFmpegPipeWriter(self.final_output, target_width, target_height,
                                      source_fps, _mode, use_nvenc=_nv,
                                      codec_family=_codec_family, quality_preset=_preset,
                                      in_pix_fmt=_in_fmt)
                if not pw.isOpened() and _nv:
                    # NVENC failed to start despite the probe -> try a CPU encode
                    pw = FFmpegPipeWriter(self.final_output, target_width, target_height,
                                          source_fps, _mode, use_nvenc=False,
                                          codec_family=_codec_family,
                                          in_pix_fmt=_in_fmt)
                if pw.isOpened():
                    out = pw
                    self._pipe_direct = True

            if out is None:
                # The legacy writer only takes BGR frames, so the YUV path is
                # off the table as soon as the direct pipe did not come up.
                if self._yuv_render:
                    self._yuv_render = False
                    print("🎨 YUV render path dropped: the direct pipe is "
                          "unavailable, the legacy writer needs BGR")
                # Legacy path: intermediate MJPEG file + final re-encode
                fourcc = cv2.VideoWriter_fourcc(*'MJPG')
                out = cv2.VideoWriter(temp_output, fourcc, source_fps, (target_width, target_height))
                if not out.isOpened():
                    raise ValueError("Could not create output video writer")
            
            # Seek to start frame
            cap.set(cv2.CAP_PROP_POS_FRAMES, actual_start)

            # ══ PASS 1: precompute the FPS/FT sequences for the DF playhead graph ══
            self._fade_enabled = bool(self.settings.get('fade_detection', False))
            # ══ PASS 1: FPS/FT sequences for the DF playhead graph ══
            self._fade_enabled = bool(self.settings.get('fade_detection', False))

            _cached = self.settings.get('load_analysis_data')
            if _cached:
                # Load the data from the file - NO re-analysis
                with open(_cached, encoding='utf-8') as f:
                    _d = json.load(f)
                self._full_fps_seq = _d['fps_seq']
                self._full_ft_seq  = _d['ft_seq']
                self._fade_excluded = set(_d.get('fade_excluded', []))
                self._full_dup_flags = _d.get('dup_flags') or [False] * len(self._full_fps_seq)
                # Apply the frame time mode to loaded data as well - older
                # .fpsdata still hold the smoothed variant.
                if (self.settings.get('frametime_mode', 'per_frame') == 'per_frame'
                        and len(self._full_dup_flags) == len(self._full_ft_seq)):
                    self._full_ft_seq = per_frame_frametimes(self._full_dup_flags,
                                                             source_fps)
                # Do NOT take the stats from the file, recompute them: older
                # .fpsdata files were still produced with the old,
                # inconsistent filters (FT contained the 1000ms sentinel).
                # The sequences themselves are unchanged and still valid.
                self._final_fps_stats, self._final_ft_stats = \
                    self._compute_final_stats(self._full_fps_seq,
                                              self._full_ft_seq, source_fps)
                print(f"📂 Analysis data loaded: {len(self._full_fps_seq)} frames "
                      f"(no re-analysis, statistics recomputed)")
                self.progress_update.emit(14, "Analysis data loaded")
            else:
                self._full_fps_seq, self._full_ft_seq, self._fade_excluded = \
                    self._prepass_collect_fps(cap, actual_start, actual_end, source_fps)
                print(f"✅ Pre-analysis finished: {len(self._full_fps_seq)} frames collected")

                # ══ PASS 1.5: VERIFICATION of the 0 fps sections ══
                # The pre-pass works on 128px NEAREST - in very calm scenes
                # real motion can fall below the threshold there and yield a
                # false 0 fps. This pass re-checks only the suspicious
                # stretches (fps~0, >=1s) at a higher resolution.
                # See verification_pass.py.
                if self.settings.get('verification_pass', True):
                    try:
                        from verification_pass import run_verification_pass
                        self.progress_update.emit(14, "Verifying the 0 fps stretches")
                        (self._full_fps_seq, self._full_ft_seq,
                         self._full_dup_flags, self._verify_report) = run_verification_pass(
                            input_file=self.input_file,
                            fps_seq=self._full_fps_seq,
                            ft_seq=self._full_ft_seq,
                            dup_flags=getattr(self, '_full_dup_flags', []),
                            source_fps=source_fps,
                            actual_start=actual_start,
                            fade_excluded=self._fade_excluded,
                            work_size=int(self.settings.get('verification_work_size', 256)),
                            use_nvdec=True,
                            uncertain_action=self.settings.get(
                                'verification_uncertain_action', 'correct'),
                            progress_cb=lambda p, t: self.progress_update.emit(
                                14 + int(p * 0.01), t),
                            is_cancelled=lambda: self.is_cancelled,
                        )
                    except Exception as e:
                        print(f"⚠️ Verification pass failed, "
                              f"pre-pass values stay unchanged: {e}")
                else:
                    print("⚪ Verification pass DISABLED (setting)")

                # ── Frame time mode ───────────────────────────────────
                # Here, because the dup_flags are only final after the
                # verification pass. 'per_frame' shows the real hold time of
                # every frame (Digital Foundry style), 'smoothed' the old
                # reciprocal of the rolling FPS.
                if self.settings.get('frametime_mode', 'per_frame') == 'per_frame':
                    _flags = getattr(self, '_full_dup_flags', None)
                    if _flags and len(_flags) == len(self._full_ft_seq):
                        self._full_ft_seq = per_frame_frametimes(_flags, source_fps)
                        _uniq = sorted(set(round(v, 1) for v in self._full_ft_seq))
                        print(f"📐 Frametime: echte Standzeit pro Frame "
                              f"(Stufen: {', '.join(f'{v}ms' for v in _uniq[:6])}"
                              f"{' …' if len(_uniq) > 6 else ''})")
                        _sc = self.settings.get('frametime_scale') or {}
                        if float(_sc.get('min', 0)) > 0.1:
                            print(f"   ⚠️ The scale starts at {_sc.get('min')}ms - "
                                  f"so the 60fps step ({1000/source_fps:.1f}ms) sits "
                                  f"exactly on the top edge. For the DF look, set "
                                  f"'frametime_scale' to a min of 0, "
                                  f"e.g. 0 / {2000/source_fps:.1f} / {4000/source_fps:.1f}.")
                    else:
                        print("⚠️ Frame time mode 'per_frame' skipped "
                              "(no matching duplicate flags)")

                # Mark fade-excluded frames as None -> a gap in the graph
                for _i in self._fade_excluded:
                    if 0 <= _i < len(self._full_fps_seq):
                        self._full_fps_seq[_i] = None
                        self._full_ft_seq[_i] = None

                # ── Deviation marker ───────────────────────────────────
                # Only here, because the frame times are not final before this.
                self._full_dev_flags = None
                if self.settings.get('deviation_marker', False):
                    _base = self.settings.get('baseline_fps', 0)
                    self._full_dev_flags = deviation_flags(
                        self._full_ft_seq, source_fps, _base,
                        hold_ms=float(self.settings.get('deviation_marker_hold_ms', 150)),
                        tolerance=float(self.settings.get('deviation_tolerance', 0.15)))
                    _n = sum(1 for x in self._full_dev_flags if x)
                    _eff = _base if _base and _base > 0 else source_fps
                    print(f"🟥 Deviation marker: {_n} of {len(self._full_dev_flags)} "
                          f"frames marked ({100*_n/max(1,len(self._full_dev_flags)):.1f}%), "
                          f"baseline {_eff:g} fps -> limit "
                          f"{1000.0/_eff*1.15:.1f} ms hold time")

                # Final statistics from the complete sequences - FPS and
                # frame time over exactly the same frame set (see
                # _stats_valid_mask), warmup via 'stats_warmup_seconds'.
                self._final_fps_stats, self._final_ft_stats = \
                    self._compute_final_stats(self._full_fps_seq,
                                              self._full_ft_seq, source_fps)

            # Seek back for the render pass
            cap.set(cv2.CAP_PROP_POS_FRAMES, actual_start)

            # ── Optionally save the analysis data (saves a re-analysis) ──
            if self.settings.get('save_analysis_data', False):
                try:
                    data_path = os.path.splitext(self.output_file)[0] + '.fpsdata'
                    payload = {
                        'version': 1,
                        'source_video': self.input_file,
                        'source_fps': source_fps,
                        'actual_start': actual_start,
                        'actual_end': actual_end,
                        'fps_seq': self._full_fps_seq,
                        'ft_seq': self._full_ft_seq,
                        'fade_excluded': sorted(self._fade_excluded),
                        'dup_flags': list(getattr(self, '_full_dup_flags', [])),
                        'fps_stats': self._final_fps_stats,
                        'ft_stats': self._final_ft_stats,
                    }
                    with open(data_path, 'w', encoding='utf-8') as f:
                        json.dump(payload, f)
                    print(f"💾 Analysis data saved: {data_path}")
                    self.progress_update.emit(15, "Analysis data saved")
                except Exception as e:
                    print(f"⚠️ Saving the analysis data failed: {e}")
            
            # Initialize analysis variables
            fps_history = collections.deque(maxlen=1000)
            frame_times = collections.deque(maxlen=180)
            
            # Pre-fill history
            for _ in range(60):
                fps_history.append(initial_fps)
                frame_times.append(initial_frame_time)

            # Setup multi-threaded encoding
            encode_queue = Queue(maxsize=120)
            self.encoding_done = False
            self.frames_encoded = 0

            def encoding_worker():
                while not self.encoding_done or not encode_queue.empty():
                    try:
                        frame = encode_queue.get(timeout=0.1)
                        if frame is not None:
                            out.write(frame)
                            self.frames_encoded += 1
                            encode_queue.task_done()
                    except:
                        continue

            encoder_thread = Thread(target=encoding_worker, daemon=True)
            encoder_thread.start()

            # Start async frame reader — prefetches next frames while we process current one
            # Render-Pass-Decoder.
            #
            # THE cv2 PATH IS THE DEFAULT - the NVDEC attempt measured
            # worse, twice in a row:
            #     cv2.VideoCapture                        53.7 fps
            #     ffmpeg NVDEC, bgr24                     29.1 fps
            #     ffmpeg NVDEC, bgr24, 16 Filter-Threads  24.4 fps
            #
            # The decode itself is not the problem - NVDEC manages 433-480 fps
            # in the pre-pass. What is expensive is everything after it:
            # swscale has to convert NV12->BGR24 on the CPU, and the result
            # has to go through a process pipe at 23.7 MB per frame.
            # cv2.VideoCapture uses the same ffmpeg libraries IN-PROCESS, so
            # it avoids the pipe copy entirely and has an optimised
            # conversion path of its own.
            #
            # The general lesson for this tool: an ffmpeg pipe pays off when
            # the output is small (pre-pass: 16 KB/frame at 128px -> 433 fps)
            # and loses when full frames have to be transported.
            #
            # The NVDEC path stays reachable via 'render_nvdec': True, in
            # case this behaves differently on other hardware.
            frame_reader = None
            if self.settings.get('render_nvdec', False) and not getattr(self, '_yuv_render', False):
                try:
                    frame_reader = FFmpegFrameReader(
                        self.input_file,
                        int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
                        int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
                        actual_start, max(0, actual_end - actual_start),
                        source_fps, use_nvdec=True,
                        decode_format=self.settings.get('render_decode_format',
                                                        'bgr24'))
                except Exception as e:
                    print(f"⚠️ NVDEC render decoder not available, "
                          f"using the cv2 fallback: {e}")
                    frame_reader = None

            # The YUV path brings its own reader: an ffmpeg pipe that hands
            # over raw I420. Software decode by default, because NVDEC does not
            # help here (see FFmpegFrameReader) - 'render_yuv_nvdec' switches
            # it on for anyone who wants to measure it on other hardware.
            if frame_reader is None and getattr(self, '_yuv_render', False):
                try:
                    frame_reader = FFmpegFrameReader(
                        self.input_file, target_width, target_height,
                        actual_start, max(0, actual_end - actual_start),
                        source_fps,
                        use_nvdec=bool(self.settings.get('render_yuv_nvdec', False)),
                        decode_format='yuv420p_raw')
                    if not getattr(frame_reader, '_raw_yuv', False):
                        # Fell back to bgr24 (odd edge length) - then the
                        # writer's format no longer matches, so stop here.
                        raise RuntimeError('reader could not deliver raw I420')
                except Exception as e:
                    print(f"⚠️ YUV reader not available ({e})")
                    frame_reader = None
                    self._yuv_render = False
                    # The writer is already running and expects yuv420p.
                    # Feeding it BGR would produce garbage, so it is restarted
                    # in BGR - that is the only way back to the standard path.
                    if self._pipe_direct and out is not None:
                        try:
                            out.release()
                        except Exception:
                            pass
                        pw = FFmpegPipeWriter(
                            self.final_output, target_width, target_height,
                            source_fps, _mode, use_nvenc=_nv,
                            codec_family=_codec_family, quality_preset=_preset,
                            in_pix_fmt='bgr24')
                        if not pw.isOpened():
                            raise RuntimeError(
                                'YUV path failed and the BGR writer could not '
                                'be restarted')
                        out = pw
                        print("↩️ Writer restarted in BGR, standard path")

            if frame_reader is None:
                cap.set(cv2.CAP_PROP_POS_FRAMES, actual_start)
                frame_reader = AsyncFrameReader(cap)
            
            # Analysis variables
            prev_frame_gray = None
            frame_count = 0
            fps_stats = IncrementalStats(warmup_frames=60)
            frametime_stats = IncrementalStats(warmup_frames=60)
            global_fps_values = collections.deque(maxlen=300)
            global_frame_times = collections.deque(maxlen=300)

            # ── Fade handling runs in the pre-pass (self._fade_excluded) ───
            displayed_fps = initial_fps
            fps_update_counter = 0
            _ui = self.settings.get('fps_update_interval')
            fps_update_interval = max(1, int(_ui)) if _ui else max(15, int(source_fps / 4))
            fps_calculation_window = collections.deque(maxlen=30)
            current_frame_number = actual_start
            
            debug_counter = 0
            
            # Main processing loop
            import time
            timing_stats = {'read': 0, 'resize': 0, 'gray': 0, 'diff': 0, 'overlay': 0, 'total': 0}

            # ══ PARALLELER RENDER-PASS (Default) ══
            use_parallel = (self.settings.get('parallel_render', True)
                            and int(self.settings.get('render_workers', 6)) >= 2)
            if use_parallel:
                self.encoding_done = True   # the sequential encoder thread is not needed
                rendered = self._run_render_parallel(
                    frame_reader, out, actual_start, actual_end, source_fps,
                    target_width, target_height, fps_update_interval, segment_frames)
                frame_count = rendered
                current_frame_number = actual_start + rendered

            while (not use_parallel) and current_frame_number < actual_end:
                t_loop_start = time.perf_counter()
                
                if self.is_cancelled:
                    break
                
                t0 = time.perf_counter()
                ret, frame = frame_reader.next_frame()
                timing_stats['read'] += time.perf_counter() - t0

                if not ret:
                    break
                
                # Process frame
                t0 = time.perf_counter()
                if self.settings.get('comparison_mode', False):
                    frame_processed = adaptive_crop_and_resize(frame, target_width, target_height, comparison_mode=True)
                else:
                    frame_processed = resize_with_aspect_ratio(frame, target_width, target_height)
                timing_stats['resize'] += time.perf_counter() - t0

                # ── Values from the PRE-PASS - no second analysis here ──
                #  (saves the greyscale conversion + duplicate detection,
                #   ~7ms/frame, and removes the duplicated 🔬/🔍 logs)
                _ri = frame_count
                is_duplicate = (self._full_dup_flags[_ri]
                                if _ri < len(self._full_dup_flags) else False)
                self.total_processed += 1
                if is_duplicate:
                    self.duplicate_count += 1
                self.detection_window.append(not is_duplicate)

                _sv = self._full_fps_seq[_ri] if _ri < len(self._full_fps_seq) else None
                if _sv is not None:
                    effective_fps = _sv
                    self._last_effective_fps = _sv
                else:
                    # Fade gap: hold the last value for the display
                    effective_fps = getattr(self, '_last_effective_fps', source_fps)
                current_frame_time = 1000.0 / effective_fps if effective_fps > 0 else 1000.0
                
                # Debug output every 100 frames
                debug_counter += 1
                if debug_counter % 100 == 0:
                    window_unique = sum(self.detection_window) if self.detection_window else 0
                    window_size = len(self.detection_window)
                    window_duplicate_count = window_size - window_unique if window_size > 0 else 0
                    unique_ratio = (window_unique / window_size * 100) if window_size > 0 else 100
                    duplicate_ratio = (self.duplicate_count / self.total_processed * 100) if self.total_processed > 0 else 0
                    
                    print(f"DEBUG Frame {debug_counter}:")
                    print(f"  Current FPS: {effective_fps:.2f} -> Frame Time: {current_frame_time:.2f}ms")
                    print(f"  Window Stats: {window_unique}/{window_size} unique ({unique_ratio:.1f}%)")
                    print(f"  Total Duplicates: {duplicate_ratio:.1f}%, Sensitivity: {self.diff_threshold}")
                    
                    # Show MIN/MAX/AVG when available
                    if global_fps_values and global_frame_times:
                        fps_min = min(global_fps_values)
                        fps_max = max(global_fps_values)
                        fps_avg = sum(global_fps_values) / len(global_fps_values)
                        ft_min = min(global_frame_times)
                        ft_max = max(global_frame_times)
                        ft_avg = sum(global_frame_times) / len(global_frame_times)
                        print(f"  GLOBAL FPS: Min={fps_min:.2f}, Max={fps_max:.2f}, Avg={fps_avg:.2f}")
                        print(f"  GLOBAL FT:  Min={ft_min:.2f}ms, Max={ft_max:.2f}ms, Avg={ft_avg:.2f}ms")
                
                # Stabilise FPS for the UI display
                stabilized_fps = self.stabilize_fps(effective_fps, source_fps)
                
                # Store values for FPS graph (always, so the line draws from frame 1)
                if not hasattr(self, '_graph_smooth_buf'):
                    _sw = max(1, int(self.settings.get('graph_smooth_window') or 1))
                    self._graph_smooth_buf = collections.deque(maxlen=_sw)
                self._graph_smooth_buf.append(effective_fps)
                fps_history.append(sum(self._graph_smooth_buf) / len(self._graph_smooth_buf))
                frame_times.append(current_frame_time)

                # Only feed stats and global history once the warm-up is done
                # (displayed_fps > 0) AND the value is physically plausible.
                # This prevents the initial detection-window ramp (where effective_fps
                # can be unrealistically low or high) from polluting MIN/MAX/AVG.
                stats_ready = (
                    frame_count > 60                          # past warm-up
                    and effective_fps > 1.0                   # at least 1 FPS
                    and effective_fps <= source_fps * 1.05    # not above source FPS
                    and current_frame_time < 2000.0           # frame time < 2 seconds
                    and current_frame_time > 0.5              # frame time > 0.5 ms
                )
                # The stats now come from the pre-pass (self._final_*_stats),
                # so no incremental accumulation is needed here any more.
                # global_fps_values/global_frame_times are still used for debug output:
                if stats_ready:
                    global_fps_values.append(effective_fps)
                    global_frame_times.append(current_frame_time)

                # Update displayed FPS with hysteresis to prevent flickering
                # between adjacent integers (e.g. 16/17 at ~16.67 FPS).
                fps_calculation_window.append(effective_fps)
                fps_update_counter += 1

                if fps_update_counter >= fps_update_interval:
                    if len(fps_calculation_window) > 0:
                        displayed_fps = round(sum(fps_calculation_window) / len(fps_calculation_window))
                    fps_update_counter = 0
                
                # First 60 frames show "---"
                if frame_count <= 60:
                    displayed_fps = -1
                
                # Prepare overlay
                show_frametime = self.settings.get('show_frametime', True)
                frametime_scale = self.settings.get('frametime_scale', {
                    'min': 16.7, 'mid': 33.3, 'max': 50.0,
                    'labels': ['16.7', '33.3', '50.0']
                })
                font_settings = self.settings.get('font_settings', {})
                color_settings = self.settings.get('color_settings', {
                    'framerate_color': '#00FF00',
                    'frametime_color': '#00FF00'
                })
                
                # Convert to RGB for overlay
                frame_rgb = cv2.cvtColor(frame_processed, cv2.COLOR_BGR2RGB)
                
                # Playhead index = position in the precomputed sequence array
                _render_idx = frame_count

                # On-the-fly statistics INCREMENTALLY: only the new value is
                # folded in per frame (no O(n^2) slice across the whole video).
                # Warmup (~1s of unstable frame rate) and fade values (None) are excluded.
                if not hasattr(self, '_run_fps_acc'):
                    self._run_fps_acc = {'sum': 0.0, 'n': 0, 'min': None, 'max': None}
                    self._run_ft_acc  = {'sum': 0.0, 'n': 0, 'min': None, 'max': None}
                    self._run_warm = int(source_fps)   # ~1s Warmup

                if _render_idx >= self._run_warm:
                    _fv = self._full_fps_seq[_render_idx] if _render_idx < len(self._full_fps_seq) else None
                    _tv = self._full_ft_seq[_render_idx]  if _render_idx < len(self._full_ft_seq)  else None
                    if _fv is not None and 1.0 < _fv <= source_fps * 1.05:
                        a = self._run_fps_acc
                        a['sum'] += _fv; a['n'] += 1
                        a['min'] = _fv if a['min'] is None else min(a['min'], _fv)
                        a['max'] = _fv if a['max'] is None else max(a['max'], _fv)
                    if _tv is not None and 0.5 < _tv < 2000.0:
                        a = self._run_ft_acc
                        a['sum'] += _tv; a['n'] += 1
                        a['min'] = _tv if a['min'] is None else min(a['min'], _tv)
                        a['max'] = _tv if a['max'] is None else max(a['max'], _tv)

                _fa, _ta = self._run_fps_acc, self._run_ft_acc
                _fps_run = ({'avg': _fa['sum']/_fa['n'], 'min': _fa['min'], 'max': _fa['max']}
                            if _fa['n'] > 0 else self._final_fps_stats)
                _ft_run  = ({'avg': _ta['sum']/_ta['n'], 'min': _ta['min'], 'max': _ta['max']}
                            if _ta['n'] > 0 else self._final_ft_stats)
                precomputed_stats = {'fps': _fps_run, 'frametime': _ft_run}

                # Create overlay (single call — was accidentally doubled before)
                t0 = time.perf_counter()
                frame_with_overlay = self.create_overlay(
                    frame_rgb, fps_history, displayed_fps, frame_times, show_frametime,
                    global_fps_values, global_frame_times, frametime_scale,
                    font_settings, color_settings, precomputed_stats,
                    playhead_index=_render_idx,
                    full_fps_seq=self._full_fps_seq,
                    full_ft_seq=self._full_ft_seq,
                    full_dev_seq=getattr(self, '_full_dev_flags', None)
                )
                timing_stats['overlay'] += time.perf_counter() - t0

                # Convert back to BGR and queue for encoding
                frame_bgr = cv2.cvtColor(frame_with_overlay, cv2.COLOR_RGB2BGR)
                try:
                    encode_queue.put(frame_bgr, timeout=0.1)
                except:
                    print("Encoding queue full, skipping frame")
                
                # Update for next iteration
                frame_count += 1
                timing_stats['total'] += time.perf_counter() - t_loop_start
                
                # Print timing every 100 frames
                if frame_count % 100 == 0:
                    print(f"⏱️ TIMING after {frame_count} frames:")
                    print(f"   read:    {timing_stats['read']*1000/frame_count:.2f}ms/frame")
                    print(f"   resize:  {timing_stats['resize']*1000/frame_count:.2f}ms/frame")
                    print(f"   gray:    {timing_stats['gray']*1000/frame_count:.2f}ms/frame")
                    print(f"   overlay: {timing_stats['overlay']*1000/frame_count:.2f}ms/frame")
                    print(f"   TOTAL:   {timing_stats['total']*1000/frame_count:.2f}ms/frame ({frame_count/timing_stats['total']:.1f} FPS)")
                current_frame_number += 1
                
                # Update progress
                progress = 15 + int((frame_count / segment_frames) * 70)                
                if frame_count % 30 == 0:
                    duplicate_ratio = (self.duplicate_count / self.total_processed * 100) if self.total_processed > 0 else 0
                    status_msg = f"Frame {current_frame_number}/{actual_end} - FPS: {effective_fps:.1f} - Duplicates: {duplicate_ratio:.1f}%"
                    self.progress_update.emit(progress, status_msg)
                
                # Send preview occasionally
                if frame_count % 50 == 0:
                    self.frame_preview.emit(frame_bgr)
            
            # Final statistics
            duplicate_percentage = (self.duplicate_count / self.total_processed * 100) if self.total_processed > 0 else 0
            unique_percentage = 100 - duplicate_percentage
            
            print(f"FRAME ANALYSIS COMPLETE:")
            print(f"  • Total frames processed: {self.total_processed}")
            print(f"  • Unique frames: {self.total_processed - self.duplicate_count} ({unique_percentage:.1f}%)")
            print(f"  • Duplicate frames: {self.duplicate_count} ({duplicate_percentage:.1f}%)")
            print(f"  • Sensitivity threshold: {self.diff_threshold}")
            if self._final_fps_stats['avg'] > 0:
                fs, ts = self._final_fps_stats, self._final_ft_stats
                print(f"  • Final FPS: Min={fs['min']:.2f}, Max={fs['max']:.2f}, Avg={fs['avg']:.2f}")
                print(f"  • Final FT: Min={ts['min']:.2f}ms, Max={ts['max']:.2f}ms, Avg={ts['avg']:.2f}ms")
            
            # Cleanup
            frame_reader.stop()
            cap.release()
            
            # Wait for encoding to finish
            print("Waiting for encoding to finish...")
            self.encoding_done = True
            encode_queue.join()
            encoder_thread.join()
            out.release()
            
            print(f"Encoding complete - {self.frames_encoded} frames")
            
            # Convert to final format
            if getattr(self, '_pipe_direct', False):
                print("🚀 Direct pipe: the final file is ready - no re-encode needed")
                self.progress_update.emit(97, "Direct encode complete!")
            elif os.path.exists(self.temp_output):
                self.progress_update.emit(90, "Converting to final format...")
                
                if self.target_bitrate_final == 'opencv':
                    # NVENC (RTX GPU) first, libx264 as the fallback
                    cmd_nvenc = [
                        'ffmpeg', '-i', self.temp_output, '-y',
                        '-c:v', 'h264_nvenc', '-preset', 'p4',
                        '-cq', '18', self.final_output
                    ]
                    cmd_x264 = [
                        'ffmpeg', '-i', self.temp_output, '-y',
                        '-c:v', 'libx264', '-preset', 'veryfast',
                        '-crf', '18', self.final_output
                    ]
                    try:
                        r = subprocess.run(cmd_nvenc, capture_output=True)
                        if r.returncode != 0:
                            print("⚠️ NVENC not available, falling back to libx264")
                            subprocess.run(cmd_x264, capture_output=True, check=True)
                        else:
                            print("🚀 NVENC encode (GPU)")
                        os.remove(self.temp_output)
                        self.progress_update.emit(95, "H264 conversion complete!")
                    except:
                        os.rename(self.temp_output, self.final_output)
                        print("FFmpeg conversion failed, using MJPEG output")
                        
                elif self.target_bitrate_final == 'prores':
                    self.progress_update.emit(92, "Creating ProRes 422 HQ...")
                    if self.ffmpeg_prores_encode(self.temp_output, self.final_output):
                        os.remove(self.temp_output)
                        self.progress_update.emit(100, "ProRes created!")
                    else:
                        os.rename(self.temp_output, self.final_output)
                        
                elif isinstance(self.target_bitrate_final, (int, str)) and str(self.target_bitrate_final).isdigit():
                    bitrate_int = int(self.target_bitrate_final)
                    cmd_nvenc = [
                        'ffmpeg', '-i', self.temp_output, '-y',
                        '-c:v', 'h264_nvenc',
                        '-b:v', f'{bitrate_int}M',
                        '-maxrate', f'{bitrate_int}M',
                        '-bufsize', f'{bitrate_int*2}M',
                        '-preset', 'p4',
                        '-movflags', '+faststart',
                        self.final_output
                    ]
                    cmd_x264 = [
                        'ffmpeg', '-i', self.temp_output, '-y',
                        '-c:v', 'libx264',
                        '-b:v', f'{bitrate_int}M',
                        '-minrate', f'{bitrate_int}M',
                        '-maxrate', f'{bitrate_int}M',
                        '-bufsize', f'{bitrate_int*2}M',
                        '-preset', 'medium',
                        '-movflags', '+faststart',
                        self.final_output
                    ]

                    try:
                        r = subprocess.run(cmd_nvenc, capture_output=True)
                        if r.returncode != 0:
                            print("⚠️ NVENC not available, falling back to libx264")
                            subprocess.run(cmd_x264, capture_output=True, check=True)
                        else:
                            print("🚀 NVENC encode (GPU)")
                        os.remove(self.temp_output)
                        self.progress_update.emit(100, f"{bitrate_int} Mbps encoding complete!")
                    except:
                        os.rename(self.temp_output, self.final_output)
                        print("FFmpeg conversion failed")

            if not self.is_cancelled:
                self.progress_update.emit(100, "Analysis completed!")
                
                # Final message with the correct statistics
                if self.total_processed > 0:
                    final_message = (f"FPS Analysis completed!\n\n"
                                   f"Detection Results:\n"
                                   f"• Sensitivity Level: {current_sensitivity}\n"
                                   f"• Unique Frames: {unique_percentage:.1f}%\n"
                                   f"• Duplicate Frames: {duplicate_percentage:.1f}%\n\n"
                                   f"Frame Time calculation now working correctly!")
                    
                    if global_fps_values and global_frame_times:
                        fps_min = min(global_fps_values)
                        fps_max = max(global_fps_values)
                        fps_avg = sum(global_fps_values) / len(global_fps_values)
                        ft_min = min(global_frame_times)
                        ft_max = max(global_frame_times)
                        ft_avg = sum(global_frame_times) / len(global_frame_times)
                        
                        final_message += (f"\n\nFinal Statistics:\n"
                                        f"• FPS: Min={fps_min:.1f}, Max={fps_max:.1f}, Avg={fps_avg:.1f}\n"
                                        f"• Frame Time: Min={ft_min:.1f}ms, Max={ft_max:.1f}ms, Avg={ft_avg:.1f}ms")
                else:
                    final_message = "FPS Analysis completed!"
                    
                self.analysis_complete.emit(True, final_message)
            else:
                self.analysis_complete.emit(False, "Analysis cancelled")
                
        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            print(f"ANALYSIS ERROR: {error_details}")
            self.analysis_complete.emit(False, f"Analysis failed: {str(e)}")