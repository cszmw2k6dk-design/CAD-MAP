"""从 last.pt 继续训练 tiles 数据集(中断后恢复用)。"""
import os

os.environ.setdefault("YOLO_CONFIG_DIR", r"C:\Users\szk\Desktop\MAP-CAD\frame_detect\yolo_config")
os.makedirs(os.environ["YOLO_CONFIG_DIR"], exist_ok=True)

from ultralytics import YOLO

LAST = r"C:\Users\szk\Desktop\MAP-CAD\frame_detect\runs\tiles\weights\last.pt"


if __name__ == "__main__":
    model = YOLO(LAST)
    model.train(resume=True)
