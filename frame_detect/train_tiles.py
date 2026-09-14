import os

os.environ.setdefault("YOLO_CONFIG_DIR", r"C:\Users\szk\Desktop\MAP-CAD\frame_detect\yolo_config")
os.makedirs(os.environ["YOLO_CONFIG_DIR"], exist_ok=True)

from ultralytics import YOLO

DATA = r"C:\Users\szk\Desktop\MAP-CAD\frame_detect\tiles\data.yaml"
PROJECT = r"C:\Users\szk\Desktop\MAP-CAD\frame_detect\runs"

model = YOLO("yolov8n.pt")
model.train(
    data=DATA,
    epochs=100,
    imgsz=768,
    batch=16,
    device="cpu",
    project=PROJECT,
    name="tiles",
    patience=20,
    workers=0,
    plots=True,
)
