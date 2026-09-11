"""
RoadSense AI - Real-Time Detection
====================================
Live webcam feed with YOLO pothole/manhole detection.

Controls:
    1       - Switch to V1 model
    2       - Switch to V2 (augmented) model
    B       - Toggle both models side-by-side
    +/-     - Increase/decrease confidence threshold
    S       - Save screenshot
    Q/ESC   - Quit
"""

import sys
import time
from pathlib import Path

try:
    from ultralytics import YOLO
except ImportError:
    print("Error: ultralytics not installed. Run: pip install ultralytics")
    sys.exit(1)

import cv2
import numpy as np

# ──────────────────────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).resolve().parent
SCREENSHOTS_DIR = BASE_DIR / "screenshots"
SCREENSHOTS_DIR.mkdir(exist_ok=True)

MODEL_PATHS = {
    "V1": BASE_DIR / "runs" / "pothole_manhole_v1" / "weights" / "best.pt",
    "V2": BASE_DIR / "runs" / "pothole_manhole_v2_augmented" / "weights" / "best.pt",
}

# Colors (BGR)
COLORS = {
    "pothole": (0, 80, 255),     # orange
    "manhole": (255, 180, 0),    # cyan-blue
}
DEFAULT_COLOR = (0, 255, 0)

# UI Colors
BG_COLOR = (30, 30, 30)
ACCENT_V1 = (0, 200, 100)
ACCENT_V2 = (0, 180, 255)
TEXT_WHITE = (255, 255, 255)
TEXT_DIM = (160, 160, 160)


# ──────────────────────────────────────────────────────────────
# Drawing Utilities
# ──────────────────────────────────────────────────────────────

def draw_rounded_rect(img, pt1, pt2, color, radius=10, thickness=-1):
    """Draw a filled rounded rectangle."""
    x1, y1 = pt1
    x2, y2 = pt2
    cv2.rectangle(img, (x1 + radius, y1), (x2 - radius, y2), color, thickness)
    cv2.rectangle(img, (x1, y1 + radius), (x2, y2 - radius), color, thickness)
    cv2.circle(img, (x1 + radius, y1 + radius), radius, color, thickness)
    cv2.circle(img, (x2 - radius, y1 + radius), radius, color, thickness)
    cv2.circle(img, (x1 + radius, y2 - radius), radius, color, thickness)
    cv2.circle(img, (x2 - radius, y2 - radius), radius, color, thickness)


def draw_detections(frame, results, label_prefix=""):
    """Draw bounding boxes and labels on the frame."""
    if results and len(results) > 0:
        boxes = results[0].boxes
        for box in boxes:
            x1, y1, x2, y2 = map(int, box.xyxy[0])
            conf = float(box.conf[0])
            cls_id = int(box.cls[0])
            cls_name = results[0].names[cls_id]

            color = COLORS.get(cls_name, DEFAULT_COLOR)

            # Bounding box
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)

            # Label background
            label = f"{label_prefix}{cls_name} {conf:.0%}"
            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 1)
            cv2.rectangle(frame, (x1, y1 - th - 10), (x1 + tw + 8, y1), color, -1)
            cv2.putText(frame, label, (x1 + 4, y1 - 5),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1, cv2.LINE_AA)

    return frame


def draw_hud(frame, model_name, conf_thresh, fps, det_count, side_by_side=False):
    """Draw the heads-up display overlay."""
    h, w = frame.shape[:2]

    # Top bar
    overlay = frame.copy()
    cv2.rectangle(overlay, (0, 0), (w, 50), BG_COLOR, -1)
    cv2.addWeighted(overlay, 0.7, frame, 0.3, 0, frame)

    # Model name
    accent = ACCENT_V2 if "V2" in model_name else ACCENT_V1
    cv2.circle(frame, (20, 25), 6, accent, -1)
    mode_text = "SIDE-BY-SIDE" if side_by_side else model_name
    cv2.putText(frame, f"  {mode_text}", (30, 32),
                cv2.FONT_HERSHEY_SIMPLEX, 0.65, TEXT_WHITE, 1, cv2.LINE_AA)

    # FPS
    fps_text = f"FPS: {fps:.1f}"
    cv2.putText(frame, fps_text, (w - 130, 32),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, TEXT_DIM, 1, cv2.LINE_AA)

    # Bottom bar
    overlay = frame.copy()
    cv2.rectangle(overlay, (0, h - 40), (w, h), BG_COLOR, -1)
    cv2.addWeighted(overlay, 0.7, frame, 0.3, 0, frame)

    # Confidence threshold
    cv2.putText(frame, f"Conf: {conf_thresh:.0%}", (10, h - 12),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, TEXT_DIM, 1, cv2.LINE_AA)

    # Detection count
    det_text = f"Detections: {det_count}"
    cv2.putText(frame, det_text, (150, h - 12),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, TEXT_DIM, 1, cv2.LINE_AA)

    # Controls hint
    controls = "[1/2] Model  [B] Both  [+/-] Conf  [S] Save  [Q] Quit"
    cv2.putText(frame, controls, (w - 520, h - 12),
                cv2.FONT_HERSHEY_SIMPLEX, 0.4, TEXT_DIM, 1, cv2.LINE_AA)

    return frame


# ──────────────────────────────────────────────────────────────
# Main Loop
# ──────────────────────────────────────────────────────────────

def main():
    print("Loading models...")

    models = {}
    for name, path in MODEL_PATHS.items():
        if not path.exists():
            print(f"Warning: {name} model not found at {path}")
            continue
        models[name] = YOLO(str(path))
        print(f"  Loaded {name}: {path.name}")

    if not models:
        print("Error: No models found!")
        sys.exit(1)

    # State
    current_model = "V2"  # Start with the better model
    conf_thresh = 0.25
    side_by_side = False
    screenshot_count = 0

    # Open webcam — try multiple backends for Windows compatibility
    print("\nOpening webcam...")
    cap = None
    backends = [
        (cv2.CAP_DSHOW, "DirectShow"),
        (cv2.CAP_MSMF, "Media Foundation"),
        (cv2.CAP_ANY, "Default"),
    ]

    for cam_idx in [0, 1]:
        for backend, backend_name in backends:
            print(f"  Trying camera {cam_idx} with {backend_name}...")
            test_cap = cv2.VideoCapture(cam_idx, backend)
            if test_cap.isOpened():
                # Try reading a test frame
                test_cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
                test_cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
                time.sleep(0.5)  # Give camera time to initialize
                ret, _ = test_cap.read()
                if ret:
                    cap = test_cap
                    print(f"  ✓ Camera {cam_idx} opened with {backend_name}")
                    break
                else:
                    test_cap.release()
            else:
                test_cap.release()
        if cap is not None:
            break

    if cap is None:
        print("Error: No working camera found.")
        print("Make sure your webcam is connected and not in use by another app.")
        sys.exit(1)

    # Warm-up: discard first few frames
    print("  Warming up camera...")
    for _ in range(10):
        cap.read()
        time.sleep(0.05)

    print("Webcam ready! Press Q or ESC to quit.\n")

    # FPS tracking
    prev_time = time.time()
    fps = 0.0

    window_name = "RoadSense AI - Real-Time Detection"
    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(window_name, 1280, 720)

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                print("Error: Failed to read frame.")
                break

            # FPS calculation
            curr_time = time.time()
            fps = 0.9 * fps + 0.1 * (1.0 / max(curr_time - prev_time, 1e-6))
            prev_time = curr_time

            if side_by_side and len(models) == 2:
                # ── Side-by-side mode ──
                frame_left = frame.copy()
                frame_right = frame.copy()

                results_v1 = models["V1"].predict(
                    source=frame_left, conf=conf_thresh,
                    imgsz=512, verbose=False
                )
                results_v2 = models["V2"].predict(
                    source=frame_right, conf=conf_thresh,
                    imgsz=512, verbose=False
                )

                frame_left = draw_detections(frame_left, results_v1)
                frame_right = draw_detections(frame_right, results_v2)

                # Add model labels
                cv2.putText(frame_left, "V1 (baseline)", (10, 30),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.8, ACCENT_V1, 2, cv2.LINE_AA)
                cv2.putText(frame_right, "V2 (augmented)", (10, 30),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.8, ACCENT_V2, 2, cv2.LINE_AA)

                # Resize for side-by-side
                h, w = frame_left.shape[:2]
                half_w = w // 2
                frame_left = cv2.resize(frame_left, (half_w, h // 2))
                frame_right = cv2.resize(frame_right, (half_w, h // 2))

                # Separator line
                sep = np.full((frame_left.shape[0], 2, 3), 255, dtype=np.uint8)
                display = np.hstack([frame_left, sep, frame_right])

                det_count = len(results_v1[0].boxes) + len(results_v2[0].boxes)
                display = draw_hud(display, "BOTH", conf_thresh, fps, det_count, side_by_side=True)

            else:
                # ── Single model mode ──
                model = models[current_model]
                results = model.predict(
                    source=frame, conf=conf_thresh,
                    imgsz=512, verbose=False
                )

                display = draw_detections(frame, results)
                det_count = len(results[0].boxes) if results else 0
                display = draw_hud(display, current_model, conf_thresh, fps, det_count)

            cv2.imshow(window_name, display)

            # ── Key handling ──
            key = cv2.waitKey(1) & 0xFF

            if key in (ord('q'), ord('Q'), 27):  # Q or ESC
                break

            elif key == ord('1'):
                current_model = "V1"
                side_by_side = False
                print(f"Switched to V1 (baseline)")

            elif key == ord('2'):
                current_model = "V2"
                side_by_side = False
                print(f"Switched to V2 (augmented)")

            elif key in (ord('b'), ord('B')):
                if len(models) == 2:
                    side_by_side = not side_by_side
                    print(f"Side-by-side: {'ON' if side_by_side else 'OFF'}")
                else:
                    print("Side-by-side requires both models loaded.")

            elif key in (ord('+'), ord('=')):
                conf_thresh = min(conf_thresh + 0.05, 0.95)
                print(f"Confidence threshold: {conf_thresh:.0%}")

            elif key in (ord('-'), ord('_')):
                conf_thresh = max(conf_thresh - 0.05, 0.05)
                print(f"Confidence threshold: {conf_thresh:.0%}")

            elif key in (ord('s'), ord('S')):
                screenshot_count += 1
                fname = SCREENSHOTS_DIR / f"detection_{screenshot_count:04d}.jpg"
                cv2.imwrite(str(fname), display)
                print(f"Screenshot saved: {fname}")

    except KeyboardInterrupt:
        print("\nInterrupted by user.")

    finally:
        cap.release()
        cv2.destroyAllWindows()
        print("Camera released. Goodbye!")


if __name__ == "__main__":
    main()
