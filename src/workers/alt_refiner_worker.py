import cv2
import numpy as np
from pathlib import Path
from PyQt6.QtCore import QRunnable, QObject, pyqtSignal


class AltRefinerSignals(QObject):
    finished = pyqtSignal(str)   # output_path
    error = pyqtSignal(str)


class AltRefinerWorker(QRunnable):
    def __init__(self, main_path, alt_path, output_path,
                 fix_color=True, auto_resize=True, manual_size=None):
        super().__init__()
        self.main_path = main_path
        self.alt_path = alt_path
        self.output_path = output_path
        self.fix_color = fix_color
        self.auto_resize = auto_resize
        self.manual_size = manual_size  # (width, height) or None
        self.signals = AltRefinerSignals()

    def run(self):
        try:
            main_img = cv2.imread(self.main_path)
            alt_img = cv2.imread(self.alt_path)
            if main_img is None or alt_img is None:
                self.signals.error.emit("Failed to load images.")
                return

            result = alt_img.copy()

            if self.manual_size:
                w, h = self.manual_size
                result = cv2.resize(result, (w, h), interpolation=cv2.INTER_LANCZOS4)
            elif self.auto_resize:
                result = self._scale_align(main_img, result)

            if self.fix_color:
                result = self._color_transfer(main_img, result)

            Path(self.output_path).parent.mkdir(parents=True, exist_ok=True)
            cv2.imwrite(self.output_path, result)
            self.signals.finished.emit(self.output_path)
        except Exception as e:
            self.signals.error.emit(str(e))

    def _scale_align(self, reference, source):
        """
        Find the per-axis scale that best overlays source onto reference using ECC,
        then output source at the largest size (at least original, at least alt).
        No translation is applied — nothing gets pushed off-frame.
        """
        h_ref, w_ref = reference.shape[:2]
        h_src, w_src = source.shape[:2]

        # Base output: stretch alt to match original's aspect ratio at the largest scale
        # (no crop — both dimensions must be >= both images' corresponding dimensions)
        # Largest scale that fits within alt's native dimensions while matching original's ratio
        k = min(w_src / w_ref, h_src / h_ref)
        w_base = round(k * w_ref)
        h_base = round(k * h_ref)

        # ECC at working resolution — both images stretched to the same size
        # so ECC captures residual content-scale mismatch, not the ratio difference
        WORK_MAX = 800
        scale_ref = min(1.0, WORK_MAX / max(w_ref, h_ref))
        ref_small = cv2.resize(reference, None, fx=scale_ref, fy=scale_ref)
        rh, rw = ref_small.shape[:2]

        src_for_ecc = cv2.resize(source, (rw, rh))

        ref_gray = cv2.cvtColor(ref_small, cv2.COLOR_BGR2GRAY)
        src_gray = cv2.cvtColor(src_for_ecc, cv2.COLOR_BGR2GRAY)

        warp_matrix = np.eye(2, 3, dtype=np.float32)
        criteria = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 500, 1e-6)

        try:
            _, warp = cv2.findTransformECC(
                ref_gray, src_gray, warp_matrix,
                cv2.MOTION_AFFINE, criteria, None, 5
            )
            # Extract only diagonal scale — ignore rotation, shear, translation
            # warp[0,0]=sx means dst pixel at x comes from src at sx*x.
            # sx>1: source is zoomed in → divide to shrink; sx<1: source is zoomed out → divide to enlarge.
            sx = float(np.clip(warp[0, 0], 0.5, 2.0))
            sy = float(np.clip(warp[1, 1], 0.5, 2.0))
            w_out = min(round(w_base / sx), w_src)
            h_out = min(round(h_base / sy), h_src)
        except cv2.error:
            w_out, h_out = w_base, h_base

        return cv2.resize(source, (w_out, h_out), interpolation=cv2.INTER_LANCZOS4)

    def _color_transfer(self, reference, source):
        """LAB color transfer — chrominance (a, b) channels only.
        Fixes color cast without altering brightness."""
        ref_f = reference.astype(np.float32) / 255.0
        src_f = source.astype(np.float32) / 255.0
        ref_lab = cv2.cvtColor(ref_f, cv2.COLOR_BGR2Lab)
        src_lab = cv2.cvtColor(src_f, cv2.COLOR_BGR2Lab)
        for i in range(1, 3):  # a and b only — skip L (lightness)
            ref_mean = ref_lab[:, :, i].mean()
            ref_std  = ref_lab[:, :, i].std()
            src_mean = src_lab[:, :, i].mean()
            src_std  = src_lab[:, :, i].std()
            if src_std > 1e-6:
                src_lab[:, :, i] = (src_lab[:, :, i] - src_mean) * (ref_std / src_std) + ref_mean
        src_lab[:, :, 1] = np.clip(src_lab[:, :, 1], -127, 127)
        src_lab[:, :, 2] = np.clip(src_lab[:, :, 2], -127, 127)
        result_f = cv2.cvtColor(src_lab, cv2.COLOR_Lab2BGR)
        return np.clip(result_f * 255.0, 0, 255).astype(np.uint8)
