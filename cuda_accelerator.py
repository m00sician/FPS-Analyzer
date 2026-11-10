"""
CUDA Accelerator for FPS Analyzer
Provides GPU-accelerated resize and template blending using PyTorch.

Falls back transparently to CPU if CUDA is unavailable.
"""

import cv2
import numpy as np
from typing import Optional, Tuple

# ── Capability detection ─────────────────────────────────────────────────────

TORCH_CUDA_AVAILABLE = False
torch = None
try:
    import torch as _torch
    if _torch.cuda.is_available():
        torch = _torch
        TORCH_CUDA_AVAILABLE = True
        print(f"✅ PyTorch CUDA: {torch.cuda.get_device_name(0)}")
    else:
        print("⚠️ PyTorch available but no CUDA device found")
except ImportError:
    print("⚠️ PyTorch not installed")

OPENCV_CUDA_AVAILABLE = False
try:
    if cv2.cuda.getCudaEnabledDeviceCount() > 0:
        # Verify resize is actually available (needs opencv-contrib CUDA build)
        _ = cv2.cuda_GpuMat()
        cv2.cuda.resize  # AttributeError if not compiled in
        OPENCV_CUDA_AVAILABLE = True
        print(f"✅ OpenCV CUDA: {cv2.cuda.getCudaEnabledDeviceCount()} device(s)")
except Exception:
    pass


# ── GPU resize ───────────────────────────────────────────────────────────────

class CUDAResizer:
    """
    Fast GPU-accelerated frame resize.

    Priority:
      1. OpenCV CUDA  – zero extra dependencies, stays in BGR
      2. PyTorch CUDA – always available if RTX card present
      3. CPU fallback – identical quality, no crash
    """

    def __init__(self):
        self.mode = self._detect_mode()
        if self.mode == 'opencv_cuda':
            self._gpu_mat = cv2.cuda_GpuMat()
            print("🚀 CUDAResizer: OpenCV CUDA mode")
        elif self.mode == 'torch':
            print("🚀 CUDAResizer: PyTorch CUDA mode")
        else:
            print("💻 CUDAResizer: CPU fallback mode")

    def _detect_mode(self) -> str:
        if OPENCV_CUDA_AVAILABLE:
            return 'opencv_cuda'
        if TORCH_CUDA_AVAILABLE:
            return 'torch'
        return 'cpu'

    def resize(self, frame: np.ndarray, target_size: Tuple[int, int],
               interpolation=cv2.INTER_LINEAR) -> np.ndarray:
        """
        Resize frame to target_size (width, height).
        Automatically uses the best available backend.
        """
        if self.mode == 'opencv_cuda':
            return self._resize_opencv_cuda(frame, target_size, interpolation)
        elif self.mode == 'torch':
            return self._resize_torch(frame, target_size)
        else:
            return cv2.resize(frame, target_size, interpolation=interpolation)

    def _resize_opencv_cuda(self, frame, target_size, interpolation):
        try:
            self._gpu_mat.upload(frame)
            gpu_resized = cv2.cuda.resize(self._gpu_mat, target_size, interpolation=interpolation)
            return gpu_resized.download()
        except Exception as e:
            print(f"⚠️ OpenCV CUDA resize failed, falling back: {e}")
            self.mode = 'cpu'
            return cv2.resize(frame, target_size, interpolation=interpolation)

    def _resize_torch(self, frame, target_size):
        try:
            tw, th = target_size
            # HWC uint8 → NCHW float on GPU
            t = torch.from_numpy(frame).cuda()          # H W C  uint8
            t = t.permute(2, 0, 1).unsqueeze(0).float() # 1 C H W float
            t = torch.nn.functional.interpolate(
                t, size=(th, tw), mode='bilinear', align_corners=False)
            t = t.squeeze(0).permute(1, 2, 0).byte()    # H W C  uint8
            return t.cpu().numpy()
        except Exception as e:
            print(f"⚠️ PyTorch resize failed, falling back: {e}")
            self.mode = 'cpu'
            return cv2.resize(frame, target_size, interpolation=cv2.INTER_LINEAR)


# ── GPU template blending ────────────────────────────────────────────────────

class CUDABlender:
    """
    GPU-accelerated alpha-composite for PNG template overlays.

    blend_template(bg, template_rgba, position) replaces the CPU loop:
        out = bg * (1 - alpha) + fg * alpha
    which is embarrassingly parallel and maps perfectly to tensor ops.
    """

    def __init__(self):
        self.mode = 'torch' if TORCH_CUDA_AVAILABLE else 'cpu'
        self._cache: dict = {}          # multi-template GPU cache
        self._roi_gpu   = None          # persistent ROI tensor (no per-frame alloc)
        self._roi_shape = None
        if self.mode == 'torch':
            print("🚀 CUDABlender: PyTorch CUDA mode")
        else:
            print("💻 CUDABlender: CPU fallback mode")

    def blend(self, bg: np.ndarray, template_rgba: np.ndarray,
              x: int, y: int) -> np.ndarray:
        """
        Alpha-composite template_rgba (H×W×4 uint8) onto bg (H×W×3 uint8)
        at pixel position (x, y). Returns bg modified in-place.
        """
        if self.mode == 'torch':
            return self._blend_torch(bg, template_rgba, x, y)
        return self._blend_cpu(bg, template_rgba, x, y)

    def _blend_torch(self, bg, template_rgba, x, y):
        try:
            th, tw = template_rgba.shape[:2]
            bh, bw = bg.shape[:2]
            x2 = min(x + tw, bw); y2 = min(y + th, bh)
            tw_c = x2 - x;        th_c = y2 - y
            if tw_c <= 0 or th_c <= 0:
                return bg
            tmpl = template_rgba[:th_c, :tw_c]

            # Multi-template cache — all templates stay on GPU permanently
            cache_key = (id(template_rgba), th_c, tw_c)
            if cache_key not in self._cache:
                t = torch.from_numpy(tmpl).cuda().float()
                self._cache[cache_key] = (t[:, :, 3:] / 255.0, t[:, :, :3])

            alpha, fg = self._cache[cache_key]

            # Persistent ROI tensor — reuse GPU allocation, no per-frame malloc
            roi_shape = (th_c, tw_c, 3)
            if self._roi_shape != roi_shape:
                self._roi_gpu   = torch.empty(roi_shape, dtype=torch.float32, device='cuda')
                self._roi_shape = roi_shape
            self._roi_gpu.copy_(torch.from_numpy(bg[y:y2, x:x2]).float())
            blended = self._roi_gpu * (1.0 - alpha) + fg * alpha
            bg[y:y2, x:x2] = blended.byte().cpu().numpy()
            return bg

        except Exception as e:
            print(f"⚠️ PyTorch blend failed, falling back: {e}")
            self.mode = 'cpu'
            return self._blend_cpu(bg, template_rgba, x, y)

    def _blend_cpu(self, bg, template_rgba, x, y):
        """Numpy CPU fallback – identical output to GPU version."""
        th, tw = template_rgba.shape[:2]
        bh, bw = bg.shape[:2]
        x2 = min(x + tw, bw)
        y2 = min(y + th, bh)
        tw_c = x2 - x
        th_c = y2 - y
        if tw_c <= 0 or th_c <= 0:
            return bg

        tmpl  = template_rgba[:th_c, :tw_c].astype(np.float32)
        alpha = tmpl[:, :, 3:] / 255.0
        fg    = tmpl[:, :, :3]
        roi   = bg[y:y2, x:x2].astype(np.float32)
        bg[y:y2, x:x2] = (roi * (1.0 - alpha) + fg * alpha).astype(np.uint8)
        return bg


# ── Legacy frame analyser (unchanged) ────────────────────────────────────────

class CUDAFrameAnalyzer:
    """
    Frame difference for duplicate detection.
    Uses optimised CPU – GPU transfer overhead makes CUDA slower here
    because images are only 128×128.
    """

    def __init__(self, use_cuda=True):
        self.use_cuda = use_cuda and TORCH_CUDA_AVAILABLE
        self._resize_size = (128, 128)
        self.frames_processed = 0
        print(f"{'🚀' if self.use_cuda else '💻'} CUDAFrameAnalyzer: "
              f"{'GPU' if self.use_cuda else 'CPU'} (CPU is faster for 128×128)")

    def calculate_frame_difference_cuda(self, current_gray, prev_gray):
        if prev_gray is None:
            return 1.0
        try:
            cur = cv2.resize(current_gray, self._resize_size, interpolation=cv2.INTER_NEAREST)
            prv = cv2.resize(prev_gray,    self._resize_size, interpolation=cv2.INTER_NEAREST)
            diff = np.abs(cur.astype(np.int16) - prv.astype(np.int16))
            self.frames_processed += 1
            return diff.mean() / 255.0
        except Exception as e:
            print(f"Frame difference error: {e}")
            return 1.0

    def get_stats(self):
        return {
            'frames_processed': self.frames_processed,
            'using_cuda': self.use_cuda,
            'mode': 'Optimized CPU (faster for small images)',
        }

    def cleanup(self):
        if TORCH_CUDA_AVAILABLE and torch is not None:
            torch.cuda.empty_cache()
            print("🧹 CUDA memory cleaned up")


def get_cuda_analyzer(use_cuda=True):
    return CUDAFrameAnalyzer(use_cuda=use_cuda)


# ── Module-level singletons (created once, reused every frame) ───────────────
_resizer: Optional[CUDAResizer]  = None
_blender: Optional[CUDABlender]  = None

def get_resizer() -> CUDAResizer:
    global _resizer
    if _resizer is None:
        _resizer = CUDAResizer()
    return _resizer

def get_blender() -> CUDABlender:
    global _blender
    if _blender is None:
        _blender = CUDABlender()
    return _blender
