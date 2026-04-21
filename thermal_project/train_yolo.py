"""
TIOS YOLO Training — Custom Thermal Anomaly Detection Model

Trains a YOLOv8 model on annotated thermal inspection images
for detecting specific thermal anomaly types.

Requires:
  - ultralytics package
  - Annotated dataset in YOLO format

Usage:
    python train_yolo.py --data ./dataset/data.yaml --epochs 100
    python train_yolo.py --resume  # Resume from last checkpoint
"""

import os
import logging
import argparse
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


# Default training configuration
DEFAULT_CONFIG = {
    "model": "yolov8n.pt",          # Base model (nano for speed, or yolov8s/m/l/x)
    "data": "./dataset/data.yaml",  # Dataset config
    "epochs": 100,
    "batch": 16,
    "imgsz": 640,
    "lr0": 0.01,
    "lrf": 0.01,                    # Final learning rate ratio
    "momentum": 0.937,
    "weight_decay": 0.0005,
    "warmup_epochs": 3.0,
    "warmup_momentum": 0.8,
    "patience": 50,                 # Early stopping patience
    "save_period": 10,              # Save checkpoint every N epochs
    "device": "cpu",                # Use "0" for GPU
    "workers": 4,
    "project": "./runs/train",
    "name": "tios_thermal",
    "exist_ok": True,
    "pretrained": True,
    "optimizer": "auto",
    "verbose": True,
    "seed": 42,
    "augment": True,
    "cache": False,
    "single_cls": False,
}

# Dataset YAML template for thermal anomaly detection
DATASET_YAML_TEMPLATE = """
# TIOS Thermal Anomaly Detection Dataset
# Place this file at: ./dataset/data.yaml

path: ./dataset                    # Dataset root directory
train: images/train                # Train images (relative to path)
val: images/val                    # Validation images
test: images/test                  # Test images (optional)

# Classes — thermal anomaly types
names:
  0: hotspot
  1: electrical_fault
  2: mechanical_fault
  3: solar_defect
  4: insulation_gap
  5: pipe_leak

# Number of classes
nc: 6
"""

# Directory structure for the dataset
DATASET_STRUCTURE = """
Expected dataset directory structure:
  dataset/
  ├── data.yaml                   # Dataset config (above template)
  ├── images/
  │   ├── train/                 # Training images (.jpg/.png)
  │   ├── val/                   # Validation images
  │   └── test/                  # Test images (optional)
  └── labels/
      ├── train/                 # YOLO format labels (.txt)
      ├── val/                   # One .txt per image
      └── test/

Label format (YOLO): 
  <class_id> <x_center> <y_center> <width> <height>
  All values are normalized (0-1) relative to image dimensions.
  
Example (hotspot at center-ish, ~10% of image):
  0 0.512 0.483 0.098 0.087
"""


def create_dataset_scaffold(base_dir: str = "./dataset"):
    """Create the dataset directory structure and template files."""
    dirs = [
        f"{base_dir}/images/train",
        f"{base_dir}/images/val",
        f"{base_dir}/images/test",
        f"{base_dir}/labels/train",
        f"{base_dir}/labels/val",
        f"{base_dir}/labels/test",
    ]
    for d in dirs:
        os.makedirs(d, exist_ok=True)
        logger.info(f"[Dataset] Created: {d}")

    # Write data.yaml
    yaml_path = os.path.join(base_dir, "data.yaml")
    if not os.path.exists(yaml_path):
        with open(yaml_path, "w") as f:
            f.write(DATASET_YAML_TEMPLATE.strip())
        logger.info(f"[Dataset] Created: {yaml_path}")

    # Write README
    readme_path = os.path.join(base_dir, "README.md")
    with open(readme_path, "w") as f:
        f.write("# TIOS Thermal Anomaly Dataset\n\n")
        f.write(DATASET_STRUCTURE)
    logger.info(f"[Dataset] Created: {readme_path}")

    print(f"\n✓ Dataset scaffold created at: {os.path.abspath(base_dir)}")
    print("  Add your annotated thermal images to images/train/ and labels/train/")
    print("  Then run: python train_yolo.py --data ./dataset/data.yaml\n")


def train(config: dict):
    """Run YOLO training with the given configuration."""
    try:
        from ultralytics import YOLO
    except ImportError:
        logger.error("ultralytics not installed. Run: pip install ultralytics")
        return None

    model_path = config["model"]
    data_path = config["data"]

    if not os.path.exists(data_path):
        logger.error(f"Dataset config not found: {data_path}")
        logger.info("Run with --scaffold to create the dataset structure first.")
        return None

    logger.info(f"[Train] Starting YOLO training")
    logger.info(f"[Train] Base model: {model_path}")
    logger.info(f"[Train] Dataset: {data_path}")
    logger.info(f"[Train] Epochs: {config['epochs']}")
    logger.info(f"[Train] Image size: {config['imgsz']}")
    logger.info(f"[Train] Device: {config['device']}")

    model = YOLO(model_path)

    results = model.train(
        data=data_path,
        epochs=config["epochs"],
        batch=config["batch"],
        imgsz=config["imgsz"],
        lr0=config["lr0"],
        lrf=config["lrf"],
        momentum=config["momentum"],
        weight_decay=config["weight_decay"],
        warmup_epochs=config["warmup_epochs"],
        patience=config["patience"],
        save_period=config["save_period"],
        device=config["device"],
        workers=config["workers"],
        project=config["project"],
        name=config["name"],
        exist_ok=config["exist_ok"],
        pretrained=config["pretrained"],
        optimizer=config["optimizer"],
        verbose=config["verbose"],
        seed=config["seed"],
        augment=config["augment"],
        cache=config["cache"],
        single_cls=config["single_cls"],
    )

    # Log results
    best_model = os.path.join(config["project"], config["name"], "weights", "best.pt")
    if os.path.exists(best_model):
        logger.info(f"[Train] ✓ Best model saved: {best_model}")
        logger.info(f"[Train] Copy this to c12_thermal_best.pt to use in the pipeline")
    else:
        logger.warning("[Train] Training may not have completed successfully")

    return results


def validate(model_path: str, data_path: str, device: str = "cpu"):
    """Run validation on the trained model."""
    try:
        from ultralytics import YOLO
    except ImportError:
        logger.error("ultralytics not installed.")
        return None

    if not os.path.exists(model_path):
        logger.error(f"Model not found: {model_path}")
        return None

    model = YOLO(model_path)
    results = model.val(data=data_path, device=device)
    logger.info(f"[Validate] mAP50: {results.box.map50:.4f}")
    logger.info(f"[Validate] mAP50-95: {results.box.map:.4f}")
    return results


def export_model(model_path: str, format: str = "onnx"):
    """Export trained model for deployment."""
    try:
        from ultralytics import YOLO
    except ImportError:
        logger.error("ultralytics not installed.")
        return None

    model = YOLO(model_path)
    model.export(format=format)
    logger.info(f"[Export] Model exported to {format} format")


def main():
    parser = argparse.ArgumentParser(description="TIOS YOLO Thermal Anomaly Training")
    parser.add_argument("--data", default="./dataset/data.yaml", help="Dataset config path")
    parser.add_argument("--model", default="yolov8n.pt", help="Base model")
    parser.add_argument("--epochs", type=int, default=100, help="Training epochs")
    parser.add_argument("--batch", type=int, default=16, help="Batch size")
    parser.add_argument("--imgsz", type=int, default=640, help="Image size")
    parser.add_argument("--device", default="cpu", help="Device (cpu, 0, cuda:0)")
    parser.add_argument("--lr", type=float, default=0.01, help="Initial learning rate")
    parser.add_argument("--resume", action="store_true", help="Resume from last checkpoint")
    parser.add_argument("--validate", default=None, help="Path to model to validate")
    parser.add_argument("--export", default=None, help="Path to model to export")
    parser.add_argument("--scaffold", action="store_true", help="Create dataset scaffold")

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(message)s",
    )

    if args.scaffold:
        create_dataset_scaffold()
        return

    if args.validate:
        validate(args.validate, args.data, args.device)
        return

    if args.export:
        export_model(args.export)
        return

    # Build training config
    config = dict(DEFAULT_CONFIG)
    config["data"] = args.data
    config["model"] = args.model
    config["epochs"] = args.epochs
    config["batch"] = args.batch
    config["imgsz"] = args.imgsz
    config["device"] = args.device
    config["lr0"] = args.lr

    if args.resume:
        last_ckpt = os.path.join(config["project"], config["name"], "weights", "last.pt")
        if os.path.exists(last_ckpt):
            config["model"] = last_ckpt
            logger.info(f"[Train] Resuming from: {last_ckpt}")
        else:
            logger.warning("[Train] No checkpoint found to resume from. Starting fresh.")

    train(config)


if __name__ == "__main__":
    main()
