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

# CUDA Accelerator für GPU-beschleunigte Frame-Analyse
try:
    from cuda_accelerator import get_cuda_analyzer, TORCH_CUDA_AVAILABLE
    CUDA_ACCELERATOR_AVAILABLE = True
    print("✅ CUDA Accelerator module loaded")
except ImportError:
    CUDA_ACCELERATOR_AVAILABLE = False
    TORCH_CUDA_AVAILABLE = False
    print("⚠️ CUDA Accelerator not available, using CPU")

class IncrementalStats:
    """Berechnet MIN/MAX/AVG inkrementell in O(1) pro Update."""
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
    # Quelle == Ziel → Resize komplett überspringen (spart ~8ms/Frame bei 4K→4K)
    h0, w0 = frame.shape[:2]
    if w0 == target_width and h0 == target_height:
        return frame
    """
    Adaptive Crop+Resize Logic for Comparison Mode with Proper Aspect Ratio
    """
    h, w = frame.shape[:2]
    
    if comparison_mode:
        # Log nur einmal pro Video
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
    """Prüft ob ffmpeg + NVENC (h264/hevc) verfügbar sind (~200ms, gecacht)."""
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
    print(f"🔎 NVENC-Probe ({enc}): {'✅ verfügbar' if ok else '❌ nicht verfügbar'}")
    return ok


class FFmpegPipeWriter:
    """
    Schreibt BGR-Frames direkt in einen ffmpeg-Encode-Prozess (stdin-Pipe).
    Spart den MJPEG-Zwischenencode + die Zwischendatei + den finalen
    Re-Encode-Pass komplett ein. API kompatibel zu cv2.VideoWriter
    (write / release / isOpened).
    """
    def __init__(self, output_path, width, height, fps, mode, use_nvenc=True,
                 codec_family='h265', quality_preset='p6'):
        """
        mode: 'cq' (Qualität, CQ ~18) oder int (Bitrate in Mbps).
        codec_family: 'h265' (HEVC, empfohlen für 4K) oder 'h264'.
        quality_preset: NVENC-Preset p1(schnell)..p7(beste Qualität).
        """
        self.ok = False
        self.failed = False
        self._proc = None
        self.frame_bytes = width * height * 3

        # ── Codec-Auswahl ──
        if use_nvenc:
            enc_name = 'hevc_nvenc' if codec_family == 'h265' else 'h264_nvenc'
            codec = ['-c:v', enc_name, '-preset', quality_preset,
                     '-rc', 'vbr', '-tune', 'hq',
                     '-spatial_aq', '1', '-temporal_aq', '1',
                     '-b_ref_mode', 'middle']
            # HEVC braucht das explizite Tag für Player-Kompatibilität
            if codec_family == 'h265':
                codec += ['-tag:v', 'hvc1']
        else:
            enc_name = 'libx265' if codec_family == 'h265' else 'libx264'
            codec = ['-c:v', enc_name, '-preset', 'medium']

        # ── Ratecontrol ──
        if mode == 'cq':
            # Qualitätsbasiert: CQ ~18, aber mit hohem Bitraten-Ceiling
            if use_nvenc:
                rate = ['-cq', '18', '-b:v', '0']
            else:
                rate = ['-crf', '18']
        else:
            b = int(mode)
            if use_nvenc:
                # VBR mit CQ-Ziel: hält die Ziel-Bitrate, darf aber bei
                # schnellen Szenen bis maxrate (2×) hochgehen → kein
                # Macroblocking mehr. bufsize großzügig für Spitzen.
                rate = ['-cq', '19',
                        '-b:v', f'{b}M',
                        '-maxrate', f'{b*2}M',
                        '-bufsize', f'{b*3}M']
            else:
                rate = ['-b:v', f'{b}M', '-maxrate', f'{int(b*1.5)}M',
                        '-bufsize', f'{b*2}M']

        cmd = ['ffmpeg', '-y',
               '-f', 'rawvideo', '-pix_fmt', 'bgr24',
               '-s', f'{width}x{height}', '-r', f'{fps}',
               '-i', '-',
               *codec, *rate,
               '-pix_fmt', 'yuv420p',        # sichere Player-Kompatibilität
               '-movflags', '+faststart',
               output_path]
        try:
            # stderr → DEVNULL: MUSS verworfen werden, sonst Pipe-Deadlock
            # unter Windows sobald der Puffer voll ist.
            self._proc = subprocess.Popen(
                cmd, stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.ok = True
            _fam = 'HEVC' if codec_family == 'h265' else 'H.264'
            _hw = 'NVENC/GPU' if use_nvenc else 'CPU'
            print(f"🚀 Direct-Pipe-Encode: {_fam} {_hw} preset={quality_preset if use_nvenc else 'medium'} → {output_path}")
        except Exception as e:
            print(f"⚠️ FFmpegPipeWriter Start fehlgeschlagen: {e}")

    def isOpened(self):
        return self.ok and not self.failed

    def write(self, frame):
        if self.failed or self._proc is None:
            return
        try:
            self._proc.stdin.write(frame.tobytes())
        except (BrokenPipeError, OSError) as e:
            self.failed = True
            print(f"❌ Pipe-Encode abgebrochen: {e}")

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
        print(f"{'✅' if ok else '❌'} Pipe-Encode beendet (rc={rc})")
        return ok


def deviation_flags(ft_seq, source_fps, baseline_fps, hold_ms=150.0, tolerance=0.15):
    """
    Markiert Frames, in denen das Material vom Baseline-Wert abweicht.

    Definition: ein Frame weicht ab, wenn seine STANDZEIT länger ist, als die
    Baseline erlaubt. Bei Baseline 60 heißt das alles über 16.7 ms, bei
    Baseline 30 alles über 33.3 ms. Damit funktioniert die Erkennung auch für
    30fps-Material in einem 60fps-Container, wo ein doppelter Frame die Norm
    und kein Fehler ist.

    Grundlage sind die echten Per-Frame-Frametimes, NICHT die gleitenden FPS.
    Die FPS sind ein 1-Sekunden-Mittel und lägen nach einem einzelnen
    Aussetzer noch eine volle Sekunde unter der Baseline — der Marker würde
    weit über das Ereignis hinaus leuchten und dessen Länge falsch darstellen.

    hold_ms: Mindest-Einblendzeit. Ein einzelner ausgelassener Frame dauert
    16-33 ms und wäre sonst kaum wahrnehmbar. Der Marker bleibt deshalb
    mindestens so lange stehen — der Startzeitpunkt verschiebt sich dadurch
    nicht.

    tolerance: Sicherheitsabstand gegen Rundung. Standzeiten sind Vielfache
    des Refresh-Intervalls, 15% liegen bequem unter dem nächsten Schritt.
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
    Echte Frametime pro Frame — aus den Duplikat-Flags statt aus den FPS.

    HINTERGRUND
    Bisher wurde die Frametime als `1000 / eff` berechnet, wobei `eff` der
    gleitende 1-Sekunden-Mittelwert der FPS ist. Damit ist die Frametime per
    Definition der Kehrwert einer geglätteten Größe — der Graph konnte gar
    nichts anderes sein als ein weiches Spiegelbild des FPS-Graphen.

    Digital Foundry zeigt dagegen die Standzeit JEDES EINZELNEN Frames. Ein
    Frame, dem k Duplikate folgen, stand (k+1) Refresh-Intervalle lang auf
    dem Bild:
        60fps-Frame (kein Duplikat) → 16.7 ms
        30fps-Frame (1 Duplikat)    → 33.3 ms
        20fps-Frame (2 Duplikate)   → 50.0 ms
    In gemischtem Material springt der Wert dadurch zwischen diesen Stufen
    hin und her — das ist die typische Rechteckwelle.

    Zum Vergleich, gemessene Sequenz aus 20 Frames 60fps gefolgt von
    40 Frames 30fps-Muster:
        per-Frame : 16.7 16.7 33.3 33.3 33.3 33.3 …   (Stufen)
        geglättet : 16.7 16.7 16.7 17.5 17.4 18.2 …   (weicher Anstieg)
    Über den 30fps-Abschnitt liefert die geglättete Variante konstant
    25.0 ms — also den Mittelwert, den es als tatsächliche Standzeit
    überhaupt nie gab.

    Der Wert gilt für die gesamte Standzeit, damit die Stufe im Graphen so
    breit ist wie der Frame wirklich stand.
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
    Liefert volle BGR-Frames über eine ffmpeg-Pipe mit NVDEC-Hardwaredecode.

    ⚠️ NICHT STANDARD — dieser Weg war in Messungen auf RTX 4090 / i9-14900K
    deutlich LANGSAMER als cv2.VideoCapture:

        cv2.VideoCapture                        53.7 fps
        ffmpeg NVDEC, bgr24                     29.1 fps
        ffmpeg NVDEC, bgr24, 16 Filter-Threads  24.4 fps

    Der Decode ist dabei nicht das Problem: derselbe NVDEC-Pfad schafft im
    Vorpass 433-480 fps. Teuer ist, was danach kommt — swscale konvertiert
    NV12→BGR24 auf der CPU, und das Ergebnis muss als 23.7 MB pro Frame
    durch eine Prozess-Pipe. cv2.VideoCapture nutzt dieselben
    ffmpeg-Bibliotheken IN-PROCESS und spart diese Kopie vollständig.

    Verallgemeinert: die ffmpeg-Pipe gewinnt, solange die Ausgabe klein ist
    (Vorpass: 128px, 16 KB/Frame → 433 fps), und verliert, sobald volle
    Frames transportiert werden.

    Erreichbar über 'render_nvdec': True, falls sich das auf anderer
    Hardware anders verhält. Der Code ist korrekt und verifiziert:

    Frame-Ausrichtung: der Seek läuft über `-ss <start/fps>`, exakt wie im
    Vorpass. Gegen cv2.CAP_PROP_POS_FRAMES geprüft (Startframes
    0/1/7/120/301/450/599): die gelieferten Frames sind BIT-IDENTISCH.

    'render_decode_format' wählt das Pipe-Format:
      'bgr24'   – Standard, bit-exakt wie cv2
      'yuv420p' – halbe Datenmenge, Konvertierung per cv2. Braucht den
                  Matrixangleich out_color_matrix=bt601, weil cv2 nur
                  BT.601 kann: ohne ihn weicht BT.709-Material um bis zu
                  41 Stufen auf 26% der Pixel ab, mit ihm um max. 11 auf
                  0.01% der Pixel.

    Skaliert wird bewusst NICHT in ffmpeg: die Python-Seite letterboxt über
    resize_with_aspect_ratio, und das in ffmpeg nachzubauen würde das Bild
    verändern.
    """

    MIN_BUFFER = 8
    MAX_BUFFER = 512
    RAM_FRACTION = 0.25

    def __init__(self, input_file, width, height, start_frame, n_frames,
                 source_fps, use_nvdec=True, decode_format='bgr24'):
        self.width = int(width)
        self.height = int(height)
        self._fmt = decode_format if decode_format in ('bgr24', 'yuv420p') else 'bgr24'
        if self._fmt == 'yuv420p' and (self.width % 2 or self.height % 2):
            # yuv420p braucht gerade Kantenlängen
            self._fmt = 'bgr24'
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

        # ── Threading für die Farbkonvertierung ─────────────────────────
        # Der erste Anlauf lief mit -pix_fmt bgr24 ohne Threading und war
        # LANGSAMER als der cv2-Pfad (29.1 statt 53.7 fps), obwohl NVDEC
        # aktiv war. Ursache ist nicht der Decode, sondern die swscale-
        # Konvertierung NV12→BGR24 auf der CPU: sie läuft einfädig und
        # schreibt 23.7 MB pro Frame. Gemessen im Container:
        #     bgr24 ohne Threads       30.6 fps
        #     bgr24 -filter_threads 8  42.3 fps   (bit-exakt identisch)
        #     yuv420p roh              73.0 fps   (aber falsche Farbmatrix)
        # -filter_threads ist der richtige Hebel, weil die Ausgabe dabei
        # bit-exakt bleibt (geprüft gegen den ungethreadeten Lauf).
        try:
            ncpu = max(2, min(16, (os.cpu_count() or 4)))
        except Exception:
            ncpu = 4
        thread_args = ['-threads', str(ncpu), '-filter_threads', str(ncpu)]

        variants = ([('NVDEC (GPU-Decode)', ['-hwaccel', 'cuda'])] if use_nvdec else [])
        variants.append(('ffmpeg-Software', []))

        for name, hw in variants:
            cmd = ['ffmpeg', '-v', 'error', *thread_args, *hw]
            if start_frame > 0 and source_fps > 0:
                cmd += ['-ss', f'{start_frame / source_fps:.6f}']
            cmd += ['-i', input_file]
            if self._n_frames > 0:
                cmd += ['-frames:v', str(self._n_frames)]
            if self._fmt == 'yuv420p':
                # Ohne Matrixangleich läse cv2 BT.709-Material als BT.601 —
                # gemessen bis zu 41 Stufen Abweichung auf 26% der Pixel.
                # Mit Angleich bleiben max. 11 auf 0.01% der Pixel.
                cmd += ['-vf', 'scale=out_color_matrix=bt601']
            cmd += ['-f', 'rawvideo', '-pix_fmt', self._fmt, '-']
            try:
                p = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                     stderr=subprocess.DEVNULL,
                                     stdin=subprocess.DEVNULL,
                                     bufsize=self._frame_bytes)
                first = self._read_exact(p.stdout, self._frame_bytes)
                if first is None:
                    raise RuntimeError('Decoder lieferte keinen Frame')
                self._proc = p
                self._first = first
                self._decoder = name
                break
            except Exception as e:
                print(f"⚠️ Render-Decoder '{name}' nicht nutzbar ({e})")
                try:
                    p.kill()
                except Exception:
                    pass

        if self._proc is None:
            raise RuntimeError('Kein ffmpeg-Decoder für den Render-Pass verfügbar')

        frame_mb = self._frame_bytes / 1024 ** 2
        print(f"📦 FFmpegFrameReader: {self._decoder}, Format {self._fmt}, "
              f"{ncpu} Filter-Threads, {buffer_size} Frames gepuffert "
              f"({frame_mb:.0f}MB × {buffer_size} = {buffer_size*frame_mb:.0f}MB RAM)")

        self._thread = Thread(target=self._reader, daemon=True)
        self._thread.start()

    @staticmethod
    def _read_exact(pipe, n):
        # bytearray, NICHT bytes: np.frombuffer auf bytes liefert ein
        # schreibgeschütztes Array. Bei Quelle == Ziel reicht
        # resize_with_aspect_ratio den Frame unverändert durch, er landet
        # also direkt in der Weiterverarbeitung — und die cv2-Frames des
        # alten Pfades waren beschreibbar. Gleiches Verhalten beibehalten.
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
            if self._fmt == 'yuv420p':
                frame = cv2.cvtColor(frame, cv2.COLOR_YUV2BGR_I420)
            self._queue.put((True, frame))
            served += 1
            data = None
            if self._n_frames and served >= self._n_frames:
                break
        # Ende signalisieren (mehrfach, falls mehrere Leser warten)
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
            return "FFmpegFrameReader: keine Reads"
        avg_fill = (self._fill_sum / self._fill_n) if self._fill_n else 0.0
        cap = self._queue.maxsize
        sp = self.starvation_pct()
        if sp > 20:
            verdict = f"DECODER ist der Flaschenhals (trotz {self._decoder})"
        elif avg_fill > cap * 0.7:
            verdict = "RENDER-WORKER sind der Flaschenhals"
        else:
            verdict = "Decoder und Worker etwa im Gleichgewicht"
        return (f"FFmpegFrameReader ({self._decoder}): {sp:.1f}% der Frames aus "
                f"leerem Puffer, mittlerer Füllstand {avg_fill:.0f}/{cap} → {verdict}")

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
        # Diagnose-Zähler (siehe next_frame/get_diagnostics)
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
        # ── Diagnose: läuft der Puffer leer? ────────────────────────────
        # Entscheidet, wo der Flaschenhals im Render-Pass liegt:
        #   Puffer regelmäßig LEER  → der Decoder kommt nicht nach. Der
        #     Render-Pass dekodiert mit cv2.VideoCapture, also in SOFTWARE
        #     und in genau EINEM Thread — anders als der Vorpass, der über
        #     ffmpeg/NVDEC läuft (deshalb dort 313 fps bei 4K).
        #   Puffer regelmäßig VOLL  → die Render-Worker sind der Flaschenhals
        #     (Overlay-Zeichnen, GIL).
        self._reads += 1
        if self._queue.empty():
            self._starved += 1
        else:
            self._fill_sum += self._queue.qsize()
            self._fill_n += 1
        return self._queue.get()

    def starvation_pct(self):
        """Anteil der Frames, die aus einem leeren Puffer geholt wurden."""
        if not self._reads:
            return 0.0
        return 100.0 * self._starved / self._reads

    def get_diagnostics(self):
        """Kurzbericht über die Puffer-Auslastung des Render-Pass-Decoders."""
        if not self._reads:
            return "AsyncFrameReader: keine Reads"
        starve_pct = 100.0 * self._starved / self._reads
        avg_fill = (self._fill_sum / self._fill_n) if self._fill_n else 0.0
        cap = self._queue.maxsize
        if starve_pct > 20:
            verdict = ("DECODER ist der Flaschenhals — cv2-Softwaredecode "
                       "single-threaded schafft das Tempo nicht")
        elif avg_fill > cap * 0.7:
            verdict = ("RENDER-WORKER sind der Flaschenhals — Decoder liefert "
                       "schneller als gezeichnet wird")
        else:
            verdict = "Decoder und Worker etwa im Gleichgewicht"
        return (f"AsyncFrameReader: {starve_pct:.1f}% der Frames aus leerem Puffer "
                f"geholt, mittlerer Füllstand {avg_fill:.0f}/{cap} → {verdict}")

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
        
        # Debug: Zeige ob Comparison-Mode aktiv ist und welche diff_threshold verwendet wird
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
        Tile-basierte Duplikat-Erkennung mit adaptivem Threshold.
        Siehe frame_detection.py für die vollständige Beschreibung:
          - 8×8 Kachel-Vergleich (robust gegen lokale Bewegung + Encoder-Rauschen)
          - Adaptiver Threshold via Largest-Gap-Clustering (robust in dunklen Szenen)
          - PairDiff-Override als Sicherheitsnetz
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

        # Diagnose alle 300 Frames — zeigt Score-Verteilung vs. Threshold
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

        # COMPARISON MODE läuft jetzt durch den vollen CodeRenderer (Layout
        # wurde vor dem Render-Loop einmalig gebaut) — hier nichts weiter nötig.

        # Get necessary configurations
        layout_config = self.settings.get('layout_config')
        template_config = dict(self.settings.get('template_config') or {})
        # Das Stats-Panel braucht die Quell-Framerate fuer die Graph-Skala.
        template_config.setdefault('source_fps',
                                   self.settings.get('source_fps', 60.0))
        
        # Falls template_config nicht definiert ist, erstellen
        if not template_config:
            template_config = {
                'fps_graph_template': self.settings.get('fps_graph_template'),
                'frametime_template': self.settings.get('frametime_template')
            }
        # Overlay-Style + Liniendicke immer aus den Settings mergen,
        # damit Layout-Editor-Einstellungen den Renderer erreichen
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
            # Basis FPS Anzeige
            text = f"FPS: {displayed_fps:.1f}" if displayed_fps >= 0 else "FPS: ---"
            font = cv2.FONT_HERSHEY_SIMPLEX
            font_scale = 2.0
            thickness = 3
            
            # Position
            (text_width, text_height), _ = cv2.getTextSize(text, font, font_scale, thickness)
            x, y = 50, 80
            
            # Schwarzer Hintergrund für bessere Lesbarkeit
            cv2.rectangle(overlay, (x-10, y-text_height-10), (x+text_width+10, y+10), (0, 0, 0), -1)
            
            # Text mit Rand
            cv2.putText(overlay, text, (x, y), font, font_scale, (0, 0, 0), thickness+2, cv2.LINE_AA)
            cv2.putText(overlay, text, (x, y), font, font_scale, (0, 255, 0), thickness, cv2.LINE_AA)
            
            # Info dass Minimal Mode aktiv ist
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
        Anzahl Frames am Segment-Anfang, die NICHT in MIN/MAX/AVG eingehen.

        Grund: das gleitende 1s-Fenster der FPS-Berechnung ist am Anfang noch
        nicht gefüllt, und der adaptive Detektor braucht Historie (MIN_HISTORY
        = 20 Frames) bevor er sinnvoll arbeitet. Werte aus dieser Phase sind
        systematisch zu niedrig und würden MIN und AVG verfälschen.

        Default 2.0s (einstellbar über 'stats_warmup_seconds').
        """
        warm_s = float(self.settings.get('stats_warmup_seconds', 2.0))
        return int(round(max(0.0, warm_s) * source_fps))

    @staticmethod
    def _stats_valid_mask(fps_seq, ft_seq, source_fps, warm_n):
        """
        Liefert die Indizes, die in MIN/MAX/AVG eingehen — für FPS und
        Frametime IDENTISCH.

        Das ist der Kern des Fixes: vorher hatten beide Statistiken eigene
        Filter (fps: 1.0 < v <= source_fps*1.05, ft: 0.5 < v < 2000.0).
        Ein Frame mit eff=0 liefert per Definition ft=1000.0 (Sentinel aus
        `ft = 1000.0/eff if eff > 0 else 1000.0`). Der FPS-Filter warf ihn
        raus, der FT-Filter ließ ihn durch → die Frametime-Statistik enthielt
        Frames, die die FPS-Statistik nicht kennt. Sichtbare Folge: MAX
        Frametime = exakt 1000.0ms und ein AVG, das nicht zum AVG der FPS
        passt (Log: FPS Avg=57.27 → müsste ~17.5ms sein, angezeigt 22.76ms).

        Jetzt entscheidet ausschließlich der FPS-Wert über die Gültigkeit;
        die Frametime folgt demselben Frame-Set.
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
        """Finale MIN/MAX/AVG für FPS und Frametime."""
        warm_n = self._stats_warmup_frames(source_fps)
        idx = self._stats_valid_mask(fps_seq, ft_seq, source_fps, warm_n)
        if not idx:
            empty = {'avg': -1, 'min': -1, 'max': -1}
            return dict(empty), dict(empty)
        f = [fps_seq[i] for i in idx]

        # ── Frametime-Stichprobe ────────────────────────────────────────
        # Im Modus 'per_frame' trägt jeder Quellframe den Wert der Standzeit,
        # zu der er gehört. Für den GRAPHEN ist das richtig — die Stufe muss
        # so breit sein wie der Frame wirklich stand. Für den MITTELWERT wäre
        # es falsch: lange Standzeiten würden mehrfach gezählt und den Wert
        # nach oben ziehen (gerechnet an einem Clip mit 21% Duplikaten:
        # 25.89 ms statt der korrekten 21.10 ms).
        # Richtig ist ein Wert pro TATSÄCHLICH PRÄSENTIERTEM Frame, also nur
        # an den Lauf-Anfängen. Probe: Gesamtzeit / Anzahl präsentierter
        # Frames = 1779 × 16.667 / 1405 = 21.10 ms — deckt sich mit dem
        # Kehrwert der mittleren FPS.
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

        print(f"📊 Statistik-Basis: {len(idx)} von {len(fps_seq)} Frames "
              f"(Warmup {warm_n} Frames = {warm_n/max(source_fps,1):.1f}s ausgeschlossen)"
              + (f", Frametime über {len(ft_idx)} präsentierte Frames"
                 if len(ft_idx) != len(idx) else ""))
        return ({'avg': sum(f)/len(f), 'min': min(f), 'max': max(f)},
                {'avg': sum(t)/len(t), 'min': min(t), 'max': max(t)})

    def _precompute_display_stats(self, source_fps, fps_update_interval):
        """
        Displayed-FPS + laufende Min/Max/Avg pro Frame VORAB berechnen.
        Macht den Render-Pass zustandslos → parallelisierbar.
        Repliziert exakt die sequentielle Logik (Update-Intervall, Warmup,
        Fade-Lücken halten letzten Wert).
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
                # FPS entscheidet über Gültigkeit, Frametime folgt demselben
                # Frame — sonst enthält die FT-Statistik den 1000ms-Sentinel
                # aus 0-fps-Frames, den die FPS-Statistik verwirft.
                tv = fts[i] if i < len(fts) else None
                valid = (sv is not None and 1.0 < sv <= source_fps * 1.05
                         and tv is not None and 0.5 < tv < 2000.0)
                if valid:
                    fa['sum'] += sv; fa['n'] += 1
                    fa['min'] = sv if fa['min'] is None else min(fa['min'], sv)
                    fa['max'] = sv if fa['max'] is None else max(fa['max'], sv)
                    # Frametime nur an präsentierten Frames zählen, sonst
                    # würden lange Standzeiten mehrfach eingehen (siehe
                    # _compute_final_stats).
                    if not (_per_frame and _flags[i]):
                        ta['sum'] += tv; ta['n'] += 1
                        ta['min'] = tv if ta['min'] is None else min(ta['min'], tv)
                        ta['max'] = tv if ta['max'] is None else max(ta['max'], tv)
            # Während der Warmup-Phase KEINE Statistik einblenden. Vorher stand
            # hier ein Fallback auf self._final_*_stats — dadurch zeigte das
            # Overlay ab Frame 0 bereits die Endwerte des ganzen Segments an,
            # also Zahlen, die zu diesem Zeitpunkt noch gar nicht gemessen sein
            # können. None lässt der Renderer bewusst aus (_draw_stats bricht
            # bei fehlenden Daten ab).
            pf[i] = ({'avg': fa['sum']/fa['n'], 'min': fa['min'], 'max': fa['max']}
                     if fa['n'] else None)
            pt[i] = ({'avg': ta['sum']/ta['n'], 'min': ta['min'], 'max': ta['max']}
                     if ta['n'] else None)
        return disp, pf, pt

    def _run_render_parallel(self, frame_reader, out, actual_start, actual_end,
                             source_fps, target_width, target_height,
                             fps_update_interval, segment_frames):
        """
        Paralleler Render-Pass: N Worker-Threads rendern Overlays, ein
        Reorder-Encoder schreibt die Frames in strikter Reihenfolge in die
        NVENC-Pipe. Möglich weil der Render-Pass durch den Vorpass
        zustandslos ist (jeder Frame hängt nur an seinem Index).
        """
        import threading as _th
        import traceback as _tb
        workers = max(2, min(12, int(self.settings.get('render_workers', 6))))
        print(f"⚡ Paralleles Rendering: {workers} Worker-Threads")

        # GPU-Blends nicht über Threads teilen → CPU-Blend (numpy, GIL-frei)
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

        # ── Stufen-Zeitmessung (thread-sicher aufsummiert) ──────────────
        # Beantwortet: geht die Zeit ins Skalieren, in die Farbkonvertierung
        # oder ins Overlay-Zeichnen? Summen über ALLE Worker, deshalb ist
        # die Summe größer als die Wanduhr-Zeit — entscheidend ist das
        # Verhältnis der Posten zueinander.
        _stage = {'resize': 0.0, 'cvt_in': 0.0, 'overlay': 0.0, 'cvt_out': 0.0}
        _stage_lock = Lock()

        def _render_one(idx, frame):
            _t = time.perf_counter()
            if comparison_mode:
                fp = adaptive_crop_and_resize(frame, target_width, target_height,
                                              comparison_mode=True)
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
                    print(f"⚠️ Render-Worker Fehler @Frame {w_idx}: {e} — Frame ohne Overlay")
                    try:
                        fb = resize_with_aspect_ratio(fr, target_width, target_height)
                    except Exception:
                        fb = np.zeros((target_height, target_width, 3), dtype=np.uint8)
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
                    # Fade-ausgeschlossene Frames sind None. Vorher wurden sie
                    # hier als "FPS: 0.0" geloggt und sahen dadurch aus wie ein
                    # echter 0-fps-Einbruch — im Overlay hält der Graph an
                    # dieser Stelle aber korrekt den letzten Wert.
                    _sv = seq[w-1] if (w-1) < len(seq) else None
                    _fps_txt = "FPS: --- (Fade)" if _sv is None else f"FPS: {_sv:.1f}"
                    dr = (self.duplicate_count / self.total_processed * 100)                          if self.total_processed else 0
                    self.progress_update.emit(
                        prog, f"Frame {actual_start + w}/{actual_end} - "
                              f"{_fps_txt} - Duplicates: {dr:.1f}%")
                if w % 50 == 0:
                    self.frame_preview.emit(fb)
                if w % 100 == 0:
                    dt = time.perf_counter() - t_start
                    print(f"⚡ PARALLEL: {w} Frames in {dt:.1f}s → "
                          f"{w/dt:.1f} FPS ({dt/w*1000:.1f}ms/Frame, {workers} Worker)")
                if disp_state['done'] and w >= disp_state['n']:
                    break

        enc_t = _th.Thread(target=_encoder, daemon=True)
        enc_t.start()

        # Frame 0 einmal SYNCHRON rendern → bg/border/Font-Caches werden vom
        # Hauptthread aufgebaut, bevor die Worker parallel loslegen.
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
            print(f"⚡ PARALLEL fertig: {idx} Frames in {dt:.1f}s "
                  f"({idx/max(dt, 1e-6):.1f} FPS, {dt/idx*1000:.1f}ms/Frame)")
            # ── Wo geht die Zeit hin? ───────────────────────────────────
            _tot = sum(_stage.values()) or 1e-9
            print(f"⏲️  Render-Pass Aufschlüsselung (Summe über {workers} Worker, "
                  f"{_tot:.1f}s Worker-Zeit für {dt:.1f}s Wanduhr):")
            for _k, _label in (('resize',  'Skalieren/Croppen'),
                               ('cvt_in',  'Farbkonvertierung BGR→RGB'),
                               ('overlay', 'Overlay zeichnen'),
                               ('cvt_out', 'Farbkonvertierung RGB→BGR')):
                _v = _stage[_k]
                print(f"     {_label:28s} {_v*1000/idx:7.2f} ms/Frame  "
                      f"({100*_v/_tot:5.1f}%)")
            _par = _tot / max(dt, 1e-9)
            # Niedrige Parallelität heißt NICHT automatisch GIL. Wenn der
            # Decoder die Worker aushungert, laufen sie zwangsläufig seriell
            # — im 4K-Lauf vom 30.07. meldete die Zeile "GIL-limitiert" bei
            # 97.8% Puffer-Leerlauf, was die Ursache falsch benannt hätte.
            try:
                _starve = frame_reader.starvation_pct()
            except Exception:
                _starve = 0.0
            if _par >= workers * 0.6:
                _verdict = "gute Skalierung"
            elif _starve > 25:
                _verdict = (f"nicht GIL — Worker warten auf den Decoder "
                            f"({_starve:.0f}% Leerlauf)")
            else:
                _verdict = "GIL-limitiert"
            print(f"     Effektive Parallelität: {_par:.2f}× von {workers} Workern "
                  f"({_verdict})")
            if _starve > 25 and _tot > 0:
                _ceiling = idx / max(_tot / workers, 1e-9)
                print(f"     Rechnerische Obergrenze ohne Decode-Limit: "
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
        Liefert 128x128-Graustufen-Frames für den Vorpass — so schnell wie möglich.
        Decode-Kette: NVDEC (GPU) → ffmpeg-Software → cv2-Fallback.

        Kern-Trick: Der Vorpass braucht NIE das volle Bild (Detektor + Fade
        arbeiten auf 128px). ffmpeg dekodiert + verkleinert + wandelt selbst
        und pipet nur 16KB/Frame statt ~24MB (4K-BGR) nach Python — der
        Vorpass ist damit nicht mehr Decode-limitiert.

        preroll: Anzahl Frames VOR actual_start, die zusätzlich vorne
        angehängt werden. Sie dienen nur dem Warmlaufen von Detektor und
        Fenster und werden vom Aufrufer verworfen (siehe
        _prepass_collect_fps). Der Aufrufer muss sicherstellen, dass
        preroll <= actual_start gilt.
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
                    raise RuntimeError('Decoder lieferte keinen Frame')
                proc, first, name_used = p, f0, name
                break
            except Exception as e:
                print(f"⚠️ Vorpass-Decoder '{name}' nicht nutzbar — nächster Fallback ({e})")
                if p is not None:
                    try:
                        p.kill()
                    except Exception:
                        pass

        if proc is not None:
            try:
                self._prepass_decoder = name_used
                print(f"⚡ Vorpass-Decoder: {name_used} (128px-Gray-Pipe)")
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

        # cv2-Fallback: alter Weg (voller Decode + Shrink in Python)
        self._prepass_decoder = 'cv2-Fallback'
        print("🐢 Vorpass-Decoder: cv2-Fallback (voller Frame-Decode)")
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
        Pass 1: Sammelt die FPS/FT-Werte pro Frame OHNE Rendering.
        Nötig für den DF-Playhead-Graphen (Render-Pass braucht die Zukunft).
        Liefert (fps_seq, ft_seq, fade_excluded_set).
        Nutzt exakt dieselbe Detektions- und Fensterlogik wie der Render-Pass.
        """
        import collections as _c
        detection_window = _c.deque(maxlen=int(source_fps))
        fps_seq, ft_seq = [], []
        dup_flags = []
        prev_gray = None
        last_eff = source_fps

        # Eigener Detektor-Zustand (getrennt vom Render-Pass)
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
            print(f"🎬 Fade-Vorpass AKTIV (std<{fade_det.std_threshold}, "
                  f"Puffer {fade_det.buffer_frames} Frames, min {fade_det.min_fade_frames} Frames)")
        else:
            print(f"⚪ Fade-Erkennung DEAKTIVIERT (Checkbox in Optionen nicht gesetzt)")

        _t_pre = time.perf_counter()
        n_expected = max(0, actual_end - actual_start)

        # ── PRE-ROLL ────────────────────────────────────────────────────
        # Ohne Vorlauf startet der Detektor bei jedem Segment "kalt": die
        # ersten MIN_HISTORY (20) Frames laufen noch mit dem User-Fallback-
        # Threshold, weil der adaptive/Low-Motion-Zweig erst ab genügend
        # Historie greift. In ruhigem Material (Scores ~0.002 gegen Fallback
        # 0.005) werden diese 20 Frames dadurch pauschal als Duplikat
        # gewertet. Das gleitende 1s-Fenster schleppt den Fehler weitere
        # 60 Frames mit — gemessen im 4K-Lauf vom 30.07.:
        #   Index 30 → 22 fps (Rechnung: (10/30)*60 = 20)
        #   Index 60 → 41 fps (Rechnung: (40/60)*60 = 40)
        #   Index 90 → 60 fps (falsche Duplikate aus dem Fenster raus)
        # Der Warmup-Ausschluss der Statistik verdeckt das nur in MIN/MAX/AVG;
        # im gerenderten Graphen blieb der Anstieg sichtbar.
        #
        # Lösung: Frames VOR dem Segmentstart mitdekodieren, damit Detektor-
        # Historie und Fenster bei Segment-Index 0 bereits gefüllt sind.
        # Größe = Fensterlänge (source_fps) + MIN_HISTORY, damit das Fenster
        # bei Index 0 ausschließlich Frames enthält, die der Detektor schon
        # mit warmer Historie klassifiziert hat.
        _preroll_want = int(source_fps) + 20
        preroll = max(0, min(_preroll_want, int(actual_start)))
        if preroll < _preroll_want:
            # Segment beginnt am (oder nahe am) Videoanfang — es gibt schlicht
            # keine Frames davor. Dann bleibt der Warmup-Effekt bestehen; die
            # Statistik fängt ihn weiterhin über stats_warmup_seconds ab.
            print(f"⚠️ Pre-Roll nur {preroll} statt {_preroll_want} Frames möglich "
                  f"(Segment startet bei Frame {actual_start}) — "
                  f"Einschwingen am Segmentanfang bleibt teilweise sichtbar")
        elif preroll:
            print(f"🔥 Pre-Roll: {preroll} Frames vor Segmentstart zum Warmlaufen "
                  f"(Detektor-Historie + 1s-Fenster), werden verworfen")

        idx = actual_start
        _fade_frame_count = 0
        _min_std_seen = 999.0
        _seen = 0          # Zähler über ALLE gelieferten Frames inkl. Pre-Roll
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
                # Detektor + Fenster sind jetzt gefüttert — dieser Frame
                # gehört aber nicht zum Segment und darf in KEINEM Ergebnis
                # auftauchen (weder Sequenzen noch Duplikat-Statistik noch
                # Fade-Erkennung, deren Indizes sonst verschoben wären).
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
                # Diagnose: kleinsten std-Wert tracken
                _s = float(gray.std())
                if _s < _min_std_seen:
                    _min_std_seen = _s

            idx += 1
            if idx % 300 == 0:
                pct = int((idx - actual_start) / max(1, actual_end - actual_start) * 12)
                self.progress_update.emit(2 + pct, f"Voranalyse {idx-actual_start}/{actual_end-actual_start}")

        # Decoder-Zählabgleich: liefert ffmpeg minimal weniger Frames als
        # erwartet, mit letztem Wert auffüllen (hält Playhead-Alignment zum
        # cv2-basierten Render-Pass).
        _got = len(fps_seq)
        if not self.is_cancelled and 0 < _got < n_expected:
            _pad = n_expected - _got
            if _pad > 5:
                print(f"⚠️ Vorpass: Decoder lieferte {_got}/{n_expected} Frames — fülle {_pad} auf")
            fps_seq.extend([fps_seq[-1]] * _pad)
            ft_seq.extend([ft_seq[-1]] * _pad)
            dup_flags.extend([False] * _pad)
        _dt_pre = time.perf_counter() - _t_pre
        if _got:
            print(f"⏱️ Vorpass: {_got} Frames in {_dt_pre:.1f}s "
                  f"({_got/max(_dt_pre, 1e-6):.0f} FPS, Decoder: {getattr(self, '_prepass_decoder', '?')})")

        if fade_det is not None:
            print(f"🔍 FADE-DIAG: {_fade_frame_count} uniforme Frames erkannt, "
                  f"niedrigster std={_min_std_seen:.2f} (Threshold={fade_det.std_threshold})")

        fade_excluded = fade_det.finalize_excluded() if fade_det is not None else set()
        if fade_det is not None:
            print(f"🎬 Fade-Vorpass: {len(fade_det.fade_blocks())} Fade(s), "
                  f"{len(fade_excluded)} Frames ausgeschlossen")

        # Detektor für den Render-Pass zurücksetzen
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

            # Comparison-Layout einmalig vorab bauen (thread-safe, vor dem
            # ggf. parallelen Render-Loop). Graph 1750x400 @ 4K, FPS-Zahl höher
            # und kleiner. Nutzt den vollen CodeRenderer → Farben/Milchglas/Style.
            if self.settings.get('comparison_mode', False):
                fw, fh = target_width, target_height
                # Auf die HÖHE normieren (4K = 2160p), damit 1750x400 bei 4K
                # wörtlich gilt — die Comparison-Frames sind nur halb so breit,
                # aber gleich hoch wie das Originalmaterial.
                s = fh / 2160.0
                gw = min(int(1750 * s), fw - int(120 * s))   # nicht breiter als Frame
                gh = int(400 * s)
                gx = int(60 * s);   gy = fh - gh - int(80 * s)
                # FPS-Zahl oben links, je 50px (4K-skaliert) vom Rand
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
                # Titel ("FRAME RATE") + Achsenlabels im Comparison etwas größer
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

            # ── Direct-Pipe-Encode (NVENC/x264) statt MJPEG-Zwischendatei ──
            # Spart Zwischenencode + Re-Encode-Pass. ProRes bleibt Legacy.
            self._pipe_direct = False
            out = None
            if self.target_bitrate_final != 'prores':
                _mode = 'cq' if self.target_bitrate_final == 'opencv' else int(self.target_bitrate_final)
                # Codec + Preset aus Settings (Default: HEVC, p6 = hohe Qualität)
                _codec_family = self.settings.get('codec_family', 'h265')
                _preset = self.settings.get('nvenc_preset', 'p6')
                _nv = _probe_nvenc(_codec_family)
                # HEVC nicht verfügbar? → auf H.264-NVENC zurückfallen
                if not _nv and _codec_family == 'h265':
                    if _probe_nvenc('h264'):
                        _codec_family = 'h264'
                        _nv = True
                pw = FFmpegPipeWriter(self.final_output, target_width, target_height,
                                      source_fps, _mode, use_nvenc=_nv,
                                      codec_family=_codec_family, quality_preset=_preset)
                if not pw.isOpened() and _nv:
                    # NVENC-Start scheiterte trotz Probe → CPU-Encode versuchen
                    pw = FFmpegPipeWriter(self.final_output, target_width, target_height,
                                          source_fps, _mode, use_nvenc=False,
                                          codec_family=_codec_family)
                if pw.isOpened():
                    out = pw
                    self._pipe_direct = True

            if out is None:
                # Legacy-Pfad: MJPEG-Zwischendatei + finaler Re-Encode
                fourcc = cv2.VideoWriter_fourcc(*'MJPG')
                out = cv2.VideoWriter(temp_output, fourcc, source_fps, (target_width, target_height))
                if not out.isOpened():
                    raise ValueError("Could not create output video writer")
            
            # Seek to start frame
            cap.set(cv2.CAP_PROP_POS_FRAMES, actual_start)

            # ══ PASS 1: FPS/FT-Sequenzen für DF-Playhead-Graph vorberechnen ══
            self._fade_enabled = bool(self.settings.get('fade_detection', False))
            # ══ PASS 1: FPS/FT-Sequenzen für DF-Playhead-Graph ══
            self._fade_enabled = bool(self.settings.get('fade_detection', False))

            _cached = self.settings.get('load_analysis_data')
            if _cached:
                # Daten aus Datei laden — KEINE Neuanalyse
                with open(_cached, encoding='utf-8') as f:
                    _d = json.load(f)
                self._full_fps_seq = _d['fps_seq']
                self._full_ft_seq  = _d['ft_seq']
                self._fade_excluded = set(_d.get('fade_excluded', []))
                self._full_dup_flags = _d.get('dup_flags') or [False] * len(self._full_fps_seq)
                # Frametime-Modus auch auf geladene Daten anwenden — ältere
                # .fpsdata enthalten noch die geglättete Variante.
                if (self.settings.get('frametime_mode', 'per_frame') == 'per_frame'
                        and len(self._full_dup_flags) == len(self._full_ft_seq)):
                    self._full_ft_seq = per_frame_frametimes(self._full_dup_flags,
                                                             source_fps)
                # Stats NICHT aus der Datei übernehmen, sondern neu rechnen:
                # ältere .fpsdata-Dateien wurden noch mit den alten,
                # inkonsistenten Filtern erzeugt (FT enthielt den 1000ms-
                # Sentinel). Die Sequenzen selbst sind unverändert gültig.
                self._final_fps_stats, self._final_ft_stats = \
                    self._compute_final_stats(self._full_fps_seq,
                                              self._full_ft_seq, source_fps)
                print(f"📂 Analyse-Daten geladen: {len(self._full_fps_seq)} Frames "
                      f"(keine Neuanalyse, Statistik neu berechnet)")
                self.progress_update.emit(14, "Analyse-Daten geladen")
            else:
                self._full_fps_seq, self._full_ft_seq, self._fade_excluded = \
                    self._prepass_collect_fps(cap, actual_start, actual_end, source_fps)
                print(f"✅ Voranalyse fertig: {len(self._full_fps_seq)} Frames gesammelt")

                # ══ PASS 1.5: VERIFIKATION der 0-fps-Sektionen ══
                # Der Vorpass arbeitet auf 128px NEAREST — in sehr ruhigen
                # Szenen kann echte Bewegung dort unter den Threshold fallen
                # und fälschlich 0 fps liefern. Dieser Pass prüft nur die
                # verdächtigen Abschnitte (fps≈0, ≥1s) in höherer Auflösung
                # nach. Siehe verification_pass.py.
                if self.settings.get('verification_pass', True):
                    try:
                        from verification_pass import run_verification_pass
                        self.progress_update.emit(14, "Verifikation der 0-fps-Abschnitte")
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
                        print(f"⚠️ Verifikations-Pass fehlgeschlagen, "
                              f"Vorpass-Werte bleiben unverändert: {e}")
                else:
                    print("⚪ Verifikations-Pass DEAKTIVIERT (Einstellung)")

                # ── Frametime-Modus ────────────────────────────────────
                # Hier, weil die dup_flags erst nach dem Verifikations-Pass
                # endgültig sind. 'per_frame' zeigt die echte Standzeit
                # jedes Frames (Digital-Foundry-Stil), 'smoothed' den alten
                # Kehrwert der gleitenden FPS.
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
                            print(f"   ⚠️ Skala beginnt bei {_sc.get('min')}ms — "
                                  f"die 60fps-Stufe ({1000/source_fps:.1f}ms) liegt "
                                  f"damit genau auf der oberen Kante. Für den "
                                  f"DF-Look 'frametime_scale' auf min 0 setzen, "
                                  f"z.B. 0 / {2000/source_fps:.1f} / {4000/source_fps:.1f}.")
                    else:
                        print("⚠️ Frametime-Modus 'per_frame' übersprungen "
                              "(keine passenden Duplikat-Flags)")

                # Fade-ausgeschlossene Frames als None markieren → Lücke im Graph
                for _i in self._fade_excluded:
                    if 0 <= _i < len(self._full_fps_seq):
                        self._full_fps_seq[_i] = None
                        self._full_ft_seq[_i] = None

                # ── Abweichungs-Marker ─────────────────────────────────
                # Erst hier, weil die Frametimes vorher nicht endgültig sind.
                self._full_dev_flags = None
                if self.settings.get('deviation_marker', False):
                    _base = self.settings.get('baseline_fps', 0)
                    self._full_dev_flags = deviation_flags(
                        self._full_ft_seq, source_fps, _base,
                        hold_ms=float(self.settings.get('deviation_marker_hold_ms', 150)),
                        tolerance=float(self.settings.get('deviation_tolerance', 0.15)))
                    _n = sum(1 for x in self._full_dev_flags if x)
                    _eff = _base if _base and _base > 0 else source_fps
                    print(f"🟥 Abweichungs-Marker: {_n} von {len(self._full_dev_flags)} "
                          f"Frames markiert ({100*_n/max(1,len(self._full_dev_flags)):.1f}%), "
                          f"Baseline {_eff:g} fps → Grenze "
                          f"{1000.0/_eff*1.15:.1f} ms Standzeit")

                # Finale Statistik aus vollständigen Sequenzen — FPS und
                # Frametime über exakt dasselbe Frame-Set (siehe
                # _stats_valid_mask), Warmup über 'stats_warmup_seconds'.
                self._final_fps_stats, self._final_ft_stats = \
                    self._compute_final_stats(self._full_fps_seq,
                                              self._full_ft_seq, source_fps)

            # Seek zurück für den Render-Pass
            cap.set(cv2.CAP_PROP_POS_FRAMES, actual_start)

            # ── Analyse-Daten optional speichern (spart Neuanalyse) ──
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
                    print(f"💾 Analyse-Daten gespeichert: {data_path}")
                    self.progress_update.emit(15, "Analyse-Daten gespeichert")
                except Exception as e:
                    print(f"⚠️ Analyse-Daten speichern fehlgeschlagen: {e}")
            
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
            # STANDARD IST DER cv2-PFAD — der NVDEC-Versuch war messbar
            # schlechter, zweimal hintereinander:
            #     cv2.VideoCapture                        53.7 fps
            #     ffmpeg NVDEC, bgr24                     29.1 fps
            #     ffmpeg NVDEC, bgr24, 16 Filter-Threads  24.4 fps
            #
            # Der Decode selbst ist nicht das Problem — NVDEC schafft im
            # Vorpass 433-480 fps. Teuer ist alles danach: swscale muss
            # NV12→BGR24 auf der CPU konvertieren, und das Ergebnis muss als
            # 23.7 MB pro Frame durch eine Prozess-Pipe. cv2.VideoCapture
            # nutzt dieselben ffmpeg-Bibliotheken IN-PROCESS, spart also die
            # Pipe-Kopie komplett und hat einen eigenen optimierten
            # Konvertierungspfad.
            #
            # Daraus die allgemeine Lehre für dieses Tool: eine ffmpeg-Pipe
            # lohnt sich, wenn die Ausgabe klein ist (Vorpass: 16 KB/Frame
            # auf 128px → 433 fps), und verliert, wenn volle Frames
            # transportiert werden müssen.
            #
            # Der NVDEC-Pfad bleibt über 'render_nvdec': True erreichbar,
            # falls sich das auf anderer Hardware anders verhält.
            frame_reader = None
            if self.settings.get('render_nvdec', False):
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
                    print(f"⚠️ NVDEC-Render-Decoder nicht verfügbar, "
                          f"nutze cv2-Fallback: {e}")
                    frame_reader = None
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

            # ── Fade-Handling läuft im Vorpass (self._fade_excluded) ───────
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
                self.encoding_done = True   # sequentieller Encoder-Thread wird nicht gebraucht
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

                # ── Werte aus dem VORPASS — keine erneute Analyse hier ──
                # (spart gray-Konvertierung + Duplikat-Erkennung, ~7ms/Frame,
                #  und beseitigt die doppelten 🔬/🔍-Logs)
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
                    # Fade-Lücke: letzten Wert für die Anzeige halten
                    effective_fps = getattr(self, '_last_effective_fps', source_fps)
                current_frame_time = 1000.0 / effective_fps if effective_fps > 0 else 1000.0
                
                # Debug-Output alle 100 Frames
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
                    
                    # Zeige MIN/MAX/AVG wenn verfügbar
                    if global_fps_values and global_frame_times:
                        fps_min = min(global_fps_values)
                        fps_max = max(global_fps_values)
                        fps_avg = sum(global_fps_values) / len(global_fps_values)
                        ft_min = min(global_frame_times)
                        ft_max = max(global_frame_times)
                        ft_avg = sum(global_frame_times) / len(global_frame_times)
                        print(f"  GLOBAL FPS: Min={fps_min:.2f}, Max={fps_max:.2f}, Avg={fps_avg:.2f}")
                        print(f"  GLOBAL FT:  Min={ft_min:.2f}ms, Max={ft_max:.2f}ms, Avg={ft_avg:.2f}ms")
                
                # Stabilize FPS für UI Display
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
                # Stats kommen jetzt aus dem Vorpass (self._final_*_stats),
                # daher hier keine inkrementelle Akkumulation mehr nötig.
                # global_fps_values/global_frame_times weiterhin für Debug-Ausgabe:
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
                
                # Playhead-Index = Position im vorberechneten Sequenz-Array
                _render_idx = frame_count

                # On-the-fly-Statistik INKREMENTELL: pro Frame wird nur der
                # neue Wert eingerechnet (kein O(n²)-Slice über das ganze Video).
                # Warmup (~1s instabile Framerate) und Fade-Werte (None) raus.
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
                print("🚀 Direct-Pipe: finale Datei fertig — kein Re-Encode nötig")
                self.progress_update.emit(97, "Direct encode complete!")
            elif os.path.exists(self.temp_output):
                self.progress_update.emit(90, "Converting to final format...")
                
                if self.target_bitrate_final == 'opencv':
                    # NVENC (RTX GPU) zuerst, libx264 als Fallback
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
                            print("⚠️ NVENC nicht verfügbar, fallback auf libx264")
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
                            print("⚠️ NVENC nicht verfügbar, fallback auf libx264")
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
                
                # Final message mit korrekten Statistiken
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