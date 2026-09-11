"""
RoadSense AI - YOLO Model Testing & Comparison Script
=====================================================
Tests pothole_manhole_v1 and pothole_manhole_v2_augmented models.
Supports evaluation on a dataset, inference on images/videos, and side-by-side comparison.

Usage:
    # Evaluate both models on a dataset
    python test_models.py eval --data path/to/data.yaml

    # Run inference on images
    python test_models.py infer --source path/to/images

    # Run inference on a video
    python test_models.py infer --source path/to/video.mp4

    # Compare both models side-by-side on images
    python test_models.py compare --source path/to/images

    # Test a single model only
    python test_models.py eval --data path/to/data.yaml --model v1
    python test_models.py eval --data path/to/data.yaml --model v2
"""

import argparse
import os
import sys
import time
from pathlib import Path

try:
    from ultralytics import YOLO
except ImportError:
    print("Error: ultralytics is not installed.")
    print("Install it with: pip install ultralytics")
    sys.exit(1)

try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False

try:
    import numpy as np
    NP_AVAILABLE = True
except ImportError:
    NP_AVAILABLE = False


# ──────────────────────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).resolve().parent
RESULTS_DIR = BASE_DIR / "test_results"

MODELS = {
    "v1": {
        "name": "pothole_manhole_v1",
        "path": BASE_DIR / "runs" / "pothole_manhole_v1" / "weights" / "best.pt",
    },
    "v2": {
        "name": "pothole_manhole_v2_augmented",
        "path": BASE_DIR / "runs" / "pothole_manhole_v2_augmented" / "weights" / "best.pt",
    },
}

# Default inference settings
DEFAULT_CONF = 0.25
DEFAULT_IOU = 0.45
DEFAULT_IMGSZ = 512


# ──────────────────────────────────────────────────────────────
# Utilities
# ──────────────────────────────────────────────────────────────

def print_header(title: str):
    """Print a formatted header."""
    width = 60
    print("\n" + "═" * width)
    print(f"  {title}")
    print("═" * width)


def print_subheader(title: str):
    """Print a formatted sub-header."""
    print(f"\n── {title} {'─' * (50 - len(title))}")


def load_model(model_key: str) -> YOLO:
    """Load a YOLO model by key (v1 or v2)."""
    info = MODELS[model_key]
    path = info["path"]
    if not path.exists():
        print(f"Error: Model not found at {path}")
        sys.exit(1)
    print(f"Loading {info['name']} from {path}")
    model = YOLO(str(path))
    return model


def get_model_keys(model_arg: str) -> list:
    """Return list of model keys to test based on user argument."""
    if model_arg == "both":
        return ["v1", "v2"]
    elif model_arg in MODELS:
        return [model_arg]
    else:
        print(f"Error: Unknown model '{model_arg}'. Choose from: v1, v2, both")
        sys.exit(1)


def ensure_dir(path: Path) -> Path:
    """Create directory if it doesn't exist and return the path."""
    path.mkdir(parents=True, exist_ok=True)
    return path


# ──────────────────────────────────────────────────────────────
# Evaluation Mode
# ──────────────────────────────────────────────────────────────

def evaluate_model(model_key: str, data_path: str, conf: float, iou: float, imgsz: int):
    """Evaluate a model on a validation dataset and return metrics."""
    info = MODELS[model_key]
    print_subheader(f"Evaluating: {info['name']}")

    model = load_model(model_key)

    start_time = time.time()
    results = model.val(
        data=data_path,
        conf=conf,
        iou=iou,
        imgsz=imgsz,
        save_json=False,
        plots=True,
        project=str(RESULTS_DIR / "eval"),
        name=info["name"],
        exist_ok=True,
    )
    elapsed = time.time() - start_time

    # Extract metrics
    metrics = {
        "model": info["name"],
        "mAP50": results.box.map50 if hasattr(results.box, "map50") else None,
        "mAP50-95": results.box.map if hasattr(results.box, "map") else None,
        "precision": results.box.mp if hasattr(results.box, "mp") else None,
        "recall": results.box.mr if hasattr(results.box, "mr") else None,
        "eval_time_sec": round(elapsed, 2),
    }

    # Per-class metrics
    if hasattr(results.box, "maps") and results.box.maps is not None:
        class_names = results.names if hasattr(results, "names") else {}
        per_class = {}
        for i, m in enumerate(results.box.maps):
            cls_name = class_names.get(i, f"class_{i}")
            per_class[cls_name] = round(float(m), 4)
        metrics["per_class_mAP50-95"] = per_class

    return metrics


def run_eval(args):
    """Run evaluation mode."""
    print_header("MODEL EVALUATION")

    if not args.data:
        print("Error: --data is required for evaluation mode.")
        print("Usage: python test_models.py eval --data path/to/data.yaml")
        sys.exit(1)

    model_keys = get_model_keys(args.model)
    all_metrics = []

    for key in model_keys:
        metrics = evaluate_model(key, args.data, args.conf, args.iou, args.imgsz)
        all_metrics.append(metrics)

    # Print results summary
    print_header("EVALUATION RESULTS SUMMARY")

    for m in all_metrics:
        print_subheader(m["model"])
        print(f"  mAP@0.5       : {m['mAP50']:.4f}" if m["mAP50"] is not None else "  mAP@0.5       : N/A")
        print(f"  mAP@0.5:0.95  : {m['mAP50-95']:.4f}" if m["mAP50-95"] is not None else "  mAP@0.5:0.95  : N/A")
        print(f"  Precision     : {m['precision']:.4f}" if m["precision"] is not None else "  Precision     : N/A")
        print(f"  Recall        : {m['recall']:.4f}" if m["recall"] is not None else "  Recall        : N/A")
        print(f"  Eval Time     : {m['eval_time_sec']}s")

        if "per_class_mAP50-95" in m:
            print("  Per-Class mAP@0.5:0.95:")
            for cls_name, val in m["per_class_mAP50-95"].items():
                print(f"    {cls_name:20s} : {val:.4f}")

    # Side-by-side comparison
    if len(all_metrics) == 2:
        print_header("SIDE-BY-SIDE COMPARISON")
        m1, m2 = all_metrics

        header = f"  {'Metric':<20s} | {'v1':>12s} | {'v2 (aug)':>12s} | {'Δ (v2-v1)':>12s}"
        print(header)
        print("  " + "─" * len(header.strip()))

        for metric_name, key in [
            ("mAP@0.5", "mAP50"),
            ("mAP@0.5:0.95", "mAP50-95"),
            ("Precision", "precision"),
            ("Recall", "recall"),
        ]:
            v1_val = m1.get(key)
            v2_val = m2.get(key)
            if v1_val is not None and v2_val is not None:
                delta = v2_val - v1_val
                arrow = "▲" if delta > 0 else "▼" if delta < 0 else "─"
                print(f"  {metric_name:<20s} | {v1_val:>12.4f} | {v2_val:>12.4f} | {arrow} {abs(delta):>10.4f}")
            else:
                print(f"  {metric_name:<20s} | {'N/A':>12s} | {'N/A':>12s} | {'N/A':>12s}")

    print(f"\nDetailed results saved to: {RESULTS_DIR / 'eval'}")


# ──────────────────────────────────────────────────────────────
# Inference Mode
# ──────────────────────────────────────────────────────────────

def run_infer(args):
    """Run inference mode on images or video."""
    print_header("MODEL INFERENCE")

    if not args.source:
        print("Error: --source is required for inference mode.")
        print("Usage: python test_models.py infer --source path/to/images_or_video")
        sys.exit(1)

    model_keys = get_model_keys(args.model)

    for key in model_keys:
        info = MODELS[key]
        print_subheader(f"Inference: {info['name']}")

        model = load_model(key)
        save_dir = ensure_dir(RESULTS_DIR / "infer" / info["name"])

        start_time = time.time()
        results = model.predict(
            source=args.source,
            conf=args.conf,
            iou=args.iou,
            imgsz=args.imgsz,
            save=True,
            save_txt=args.save_labels,
            save_conf=args.save_labels,
            project=str(RESULTS_DIR / "infer"),
            name=info["name"],
            exist_ok=True,
        )
        elapsed = time.time() - start_time

        # Print detection summary
        total_detections = 0
        class_counts = {}
        for r in results:
            boxes = r.boxes
            total_detections += len(boxes)
            for cls_id in boxes.cls:
                cls_name = r.names[int(cls_id)]
                class_counts[cls_name] = class_counts.get(cls_name, 0) + 1

        print(f"\n  Total images/frames processed : {len(results)}")
        print(f"  Total detections              : {total_detections}")
        print(f"  Inference time                : {elapsed:.2f}s")
        if len(results) > 0:
            print(f"  Avg time per image            : {elapsed / len(results) * 1000:.1f}ms")

        if class_counts:
            print("  Detection counts by class:")
            for cls_name, count in sorted(class_counts.items()):
                print(f"    {cls_name:20s} : {count}")

        print(f"  Results saved to: {save_dir}")


# ──────────────────────────────────────────────────────────────
# Compare Mode (side-by-side visual comparison)
# ──────────────────────────────────────────────────────────────

def run_compare(args):
    """Run side-by-side visual comparison of both models on the same images."""
    print_header("SIDE-BY-SIDE VISUAL COMPARISON")

    if not args.source:
        print("Error: --source is required for compare mode.")
        print("Usage: python test_models.py compare --source path/to/images")
        sys.exit(1)

    if not CV2_AVAILABLE or not NP_AVAILABLE:
        print("Error: opencv-python and numpy are required for compare mode.")
        print("Install with: pip install opencv-python numpy")
        sys.exit(1)

    # Load both models
    model_v1 = load_model("v1")
    model_v2 = load_model("v2")

    save_dir = ensure_dir(RESULTS_DIR / "compare")

    # Gather images
    source_path = Path(args.source)
    if source_path.is_file():
        image_paths = [source_path]
    elif source_path.is_dir():
        extensions = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tiff"}
        image_paths = sorted([p for p in source_path.iterdir() if p.suffix.lower() in extensions])
    else:
        print(f"Error: Source not found: {args.source}")
        sys.exit(1)

    if not image_paths:
        print("Error: No images found in the source path.")
        sys.exit(1)

    print(f"  Found {len(image_paths)} image(s) to compare.\n")

    for img_path in image_paths:
        print(f"  Processing: {img_path.name}")

        # Run inference with both models
        results_v1 = model_v1.predict(
            source=str(img_path), conf=args.conf, iou=args.iou,
            imgsz=args.imgsz, verbose=False,
        )
        results_v2 = model_v2.predict(
            source=str(img_path), conf=args.conf, iou=args.iou,
            imgsz=args.imgsz, verbose=False,
        )

        # Get annotated images
        img_v1 = results_v1[0].plot()
        img_v2 = results_v2[0].plot()

        # Resize to same height for side-by-side
        h1, w1 = img_v1.shape[:2]
        h2, w2 = img_v2.shape[:2]
        target_h = max(h1, h2)

        if h1 != target_h:
            scale = target_h / h1
            img_v1 = cv2.resize(img_v1, (int(w1 * scale), target_h))
        if h2 != target_h:
            scale = target_h / h2
            img_v2 = cv2.resize(img_v2, (int(w2 * scale), target_h))

        # Add labels
        label_h = 40
        label_v1 = np.zeros((label_h, img_v1.shape[1], 3), dtype=np.uint8)
        label_v2 = np.zeros((label_h, img_v2.shape[1], 3), dtype=np.uint8)
        cv2.putText(label_v1, "V1 (baseline)", (10, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
        cv2.putText(label_v2, "V2 (augmented)", (10, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 200, 255), 2)

        img_v1_labeled = np.vstack([label_v1, img_v1])
        img_v2_labeled = np.vstack([label_v2, img_v2])

        # Create separator
        separator = np.ones((img_v1_labeled.shape[0], 4, 3), dtype=np.uint8) * 255

        # Combine side by side
        combined = np.hstack([img_v1_labeled, separator, img_v2_labeled])

        # Save
        output_path = save_dir / f"compare_{img_path.stem}.jpg"
        cv2.imwrite(str(output_path), combined)
        print(f"    Saved: {output_path.name}")

        # Print detection counts
        n_v1 = len(results_v1[0].boxes)
        n_v2 = len(results_v2[0].boxes)
        print(f"    V1 detections: {n_v1}  |  V2 detections: {n_v2}")

    print(f"\n  Comparison images saved to: {save_dir}")


# ──────────────────────────────────────────────────────────────
# Argument Parser
# ──────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="RoadSense AI - YOLO Model Testing & Comparison",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python test_models.py eval --data dataset/data.yaml
  python test_models.py infer --source test_images/
  python test_models.py infer --source video.mp4 --model v2
  python test_models.py compare --source test_images/ --conf 0.3
        """,
    )

    subparsers = parser.add_subparsers(dest="mode", help="Testing mode")

    # ── Eval subcommand ──
    eval_parser = subparsers.add_parser("eval", help="Evaluate model(s) on a validation dataset")
    eval_parser.add_argument("--data", type=str, required=True, help="Path to data.yaml for evaluation")
    eval_parser.add_argument("--model", type=str, default="both", choices=["v1", "v2", "both"],
                             help="Which model to test (default: both)")
    eval_parser.add_argument("--conf", type=float, default=DEFAULT_CONF, help="Confidence threshold")
    eval_parser.add_argument("--iou", type=float, default=DEFAULT_IOU, help="IoU threshold")
    eval_parser.add_argument("--imgsz", type=int, default=DEFAULT_IMGSZ, help="Image size")

    # ── Infer subcommand ──
    infer_parser = subparsers.add_parser("infer", help="Run inference on images or video")
    infer_parser.add_argument("--source", type=str, required=True, help="Path to image, folder, or video")
    infer_parser.add_argument("--model", type=str, default="both", choices=["v1", "v2", "both"],
                              help="Which model to use (default: both)")
    infer_parser.add_argument("--conf", type=float, default=DEFAULT_CONF, help="Confidence threshold")
    infer_parser.add_argument("--iou", type=float, default=DEFAULT_IOU, help="IoU threshold")
    infer_parser.add_argument("--imgsz", type=int, default=DEFAULT_IMGSZ, help="Image size")
    infer_parser.add_argument("--save-labels", action="store_true", help="Save detection labels as .txt files")

    # ── Compare subcommand ──
    compare_parser = subparsers.add_parser("compare", help="Side-by-side visual comparison of both models")
    compare_parser.add_argument("--source", type=str, required=True, help="Path to image or folder")
    compare_parser.add_argument("--conf", type=float, default=DEFAULT_CONF, help="Confidence threshold")
    compare_parser.add_argument("--iou", type=float, default=DEFAULT_IOU, help="IoU threshold")
    compare_parser.add_argument("--imgsz", type=int, default=DEFAULT_IMGSZ, help="Image size")

    args = parser.parse_args()

    if args.mode is None:
        parser.print_help()
        sys.exit(0)

    # Verify models exist
    for key, info in MODELS.items():
        if not info["path"].exists():
            print(f"Warning: Model '{info['name']}' not found at {info['path']}")

    # Dispatch
    if args.mode == "eval":
        run_eval(args)
    elif args.mode == "infer":
        run_infer(args)
    elif args.mode == "compare":
        run_compare(args)


if __name__ == "__main__":
    main()
