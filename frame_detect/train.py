import os

# 让 ultralytics 把配置/缓存写到工作区，避免写 AppData 被拒
os.environ.setdefault("YOLO_CONFIG_DIR", r"C:\Users\szk\Desktop\MAP-CAD\frame_detect\yolo_config")
os.makedirs(os.environ["YOLO_CONFIG_DIR"], exist_ok=True)

from ultralytics import YOLO

DATA = r"C:\Users\szk\Desktop\MAP-CAD\frame_detect\data.yaml"
PROJECT = r"C:\Users\szk\Desktop\MAP-CAD\frame_detect\runs"

model = YOLO("yolov8n.pt")  # 首次自动下载权重
model.train(
    data=DATA,
    epochs=60,
    imgsz=640,
    batch=16,
    device="cpu",
    project=PROJECT,
    name="frames",
    patience=12,
    workers=0,
    plots=True,
)
