import os, shutil, random, yaml
from pathlib import Path

"""
STEP 1 — Get the FLIR Thermal Dataset (free)
  https://www.flir.com/oem/adas/adas-dataset-form/
  Contains ~14,000 annotated thermal images: people, cars, bicycles

STEP 2 — Install requirements
  pip install ultralytics torch torchvision

STEP 3 — Folder structure expected:
  thermal_dataset/
    images/
      train/   ← .jpg thermal images
      val/
    labels/
      train/   ← YOLO .txt annotations (class cx cy w h normalised)
      val/

STEP 4 — Run this script:
  python train_yolo.py

STEP 5 — After training, best weights at:
  runs/detect/c12_thermal/weights/best.pt
  → copy to project root and update classifier.py model_path
"""

# ── Dataset config ──────────────────────────────────────────
DATASET_ROOT = "thermal_dataset"
YAML_PATH    = "c12_thermal.yaml"

# 3 target classes (rocks/ground already excluded at detection stage)
CLASSES = ["human", "animal", "vehicle"]

# ── Training hyperparameters tuned for C12 384x288 sensor ───
IMG_SIZE   = 320   # close to native 384x288, fast inference on Jetson
EPOCHS     = 80
BATCH_SIZE = 16    # reduce to 8 if GPU VRAM < 6GB
BASE_MODEL = "yolov8n.pt"  # nano = fastest; use yolov8s.pt for +accuracy
PROJECT    = "runs/detect"
RUN_NAME   = "c12_thermal"

def build_yaml():
    # Write dataset YAML that ultralytics expects
    cfg = {
        "path"  : os.path.abspath(DATASET_ROOT),
        "train" : "images/train",
        "val"   : "images/val",
        "nc"    : len(CLASSES),
        "names" : CLASSES,
    }
    with open(YAML_PATH, "w") as f:
        yaml.dump(cfg, f, default_flow_style=False)
    print(f"[TRAIN] Dataset YAML written → {YAML_PATH}")

def remap_flir_labels(flir_labels_dir, output_dir):
    """
    FLIR dataset uses COCO IDs. Remap to our 3 classes:
      COCO 0  (person)     → 0 human
      COCO 2  (car)        → 2 vehicle
      COCO 17 (cat) etc.   → 1 animal
    """
    FLIR_REMAP = {
        0:0,                          # person → human
        2:2, 3:2, 5:2, 7:2,          # car/moto/bus/truck → vehicle
        14:1,15:1,16:1,17:1,18:1,   # bird/cat/dog/horse/sheep → animal
        19:1,20:1,21:1,22:1,23:1,   # cow/elephant/bear/zebra/giraffe
    }
    os.makedirs(output_dir, exist_ok=True)
    for txt in Path(flir_labels_dir).glob("*.txt"):
        lines_out = []
        with open(txt) as f:
            for line in f:
                parts = line.strip().split()
                if not parts: continue
                cid = int(parts[0])
                if cid in FLIR_REMAP:
                    parts[0] = str(FLIR_REMAP[cid])
                    lines_out.append(" ".join(parts))
        if lines_out:
            out_path = os.path.join(output_dir, txt.name)
            with open(out_path, "w") as f:
                f.write("\n".join(lines_out))

def augment_config():
    # Extra augmentation args for thermal: no colour jitter, more flip/scale
    return {
        "hsv_h"   : 0.0,  # thermal has no hue
        "hsv_s"   : 0.0,  # no saturation
        "hsv_v"   : 0.3,  # intensity variation (emissivity differences)
        "fliplr"  : 0.5,
        "flipud"  : 0.1,
        "scale"   : 0.5,
        "translate": 0.1,
        "mosaic"  : 1.0,
        "mixup"   : 0.1,
    }

def train():
    from ultralytics import YOLO

    build_yaml()

    model = YOLO(BASE_MODEL)

    print(f"[TRAIN] Starting — {EPOCHS} epochs, img {IMG_SIZE}, batch {BATCH_SIZE}")
    results = model.train(
        data       = YAML_PATH,
        epochs     = EPOCHS,
        imgsz      = IMG_SIZE,
        batch      = BATCH_SIZE,
        project    = PROJECT,
        name       = RUN_NAME,
        device     = "0",        # GPU 0; use "cpu" if no GPU
        patience   = 20,         # early stopping
        save       = True,
        plots      = True,
        verbose    = True,
        **augment_config()
    )

    best = Path(PROJECT) / RUN_NAME / "weights" / "best.pt"
    shutil.copy(best, "c12_thermal_best.pt")
    print(f"[TRAIN] Done! Best weights → c12_thermal_best.pt")
    print(f"[TRAIN] Update classifier.py: model_path='c12_thermal_best.pt'")

def validate():
    from ultralytics import YOLO
    model = YOLO("c12_thermal_best.pt")
    metrics = model.val(data=YAML_PATH, imgsz=IMG_SIZE)
    print(f"mAP50: {metrics.box.map50:.3f}")
    print(f"mAP50-95: {metrics.box.map:.3f}")

if __name__ == "__main__":
    train()
    validate()