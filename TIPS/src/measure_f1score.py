이 파일은 정밀도(Precision)와 재현율(Recall)의 조화 평균인 F1-Score를 측정합니다. measure_mAP.py와 마찬가지로 YOLO의 내장 검증 기능을 활용하기 위해 임시 데이터셋을 생성합니다.
import numpy as np
np.bool = bool 
np.float = float

import argparse
import json
import os
import csv
import shutil
from pathlib import Path
from ultralytics import YOLO

def prepare_yolo_dataset(image_dir, label_dir, tmp_dir):
    """
    mAP 측정 파일과 동일하게 JSON 정답 데이터를 YOLO .txt 및 .yaml 형식으로 변환합니다.
    F1-Score 계산을 위해 동일한 데이터셋 구성이 필요하기 때문입니다.
    """
    os.makedirs(tmp_dir, exist_ok=True)
    label_out_dir = Path(tmp_dir) / "labels" / "test"
    label_out_dir.mkdir(parents=True, exist_ok=True)

    image_files = list(Path(image_dir).glob('*.jpg')) + \
                      list(Path(image_dir).glob('*.jpeg')) + \
                      list(Path(image_dir).glob('*.png'))
    
    img_w, img_h = 1920, 1080
    class_map = {"Human": 0, "Car": 1}
    
    for img_path in image_files:
        label_file = Path(label_dir) / f"{img_path.stem}.json"
        if not label_file.exists():
            continue

        with open(label_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            annotations = data.get("Learning_Data_Info.", {}).get("Annotations", [])

        yolo_annots = []
        for ann in annotations:
            cls_id = ann.get("Class_ID")
            if cls_id not in class_map:
                continue
            
            cls_num = class_map[cls_id]
            type_val = ann.get("Type_value", [])
            
            # YOLO 정규화 좌표 계산
            x_center = (type_val[0] + type_val[2]) / 2 / img_w
            y_center = (type_val[1] + type_val[3]) / 2 / img_h
            width = (type_val[2] - type_val[0]) / img_w
            height = (type_val[3] - type_val[1]) / img_h
            
            yolo_annots.append(f"{cls_num} {x_center:.6f} {y_center:.6f} {width:.6f} {height:.6f}")

        with open(label_out_dir / f"{img_path.stem}.txt", 'w') as f:
            f.write("\n".join(yolo_annots))

    img_out_dir = Path(tmp_dir) / "images" / "test"
    img_out_dir.mkdir(parents=True, exist_ok=True)
    for img_path in image_files:
        (img_out_dir / img_path.name).symlink_to(img_path.resolve())

    yaml_content = f"""path: {tmp_dir}
train: images/test
val: images/test
test: images/test 
names:
  0: Human
  1: Car
"""
    yaml_path = Path(tmp_dir) / "test_dataset.yaml"
    with open(yaml_path, 'w') as f:
        f.write(yaml_content)
    
    return yaml_path

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model_path", required=True, type=str, help="Path to .pt model file")
    parser.add_argument("--image_dir", default="./ob_testset/inputs/image/", type=str)
    parser.add_argument("--label_dir", default="./ob_testset/inputs/label/", type=str)
    parser.add_argument("--output_csv", default="./ob_testset/f1score_result.csv", type=str)
    args = parser.parse_args()

    tmp_dir = "/tmp/yolo_val_f1"
    if os.path.exists(tmp_dir):
        shutil.rmtree(tmp_dir)

    try:
        # 1. YOLO 형식의 임시 데이터셋을 준비합니다.
        yaml_path = prepare_yolo_dataset(args.image_dir, args.label_dir, tmp_dir)

        # 2. 모델을 로드하고 val()을 통해 내부적으로 Precision, Recall, F1-Score를 계산합니다.
        model = YOLO(args.model_path, task='detect')
        results = model.val(data=str(yaml_path), split='test', plots=False, verbose=False, batch=3)

        # 3. 모든 클래스의 평균 F1-Score 값을 추출합니다.
        f1_score = results.box.f1.mean() 

        # 결과를 CSV 파일로 저장합니다.
        with open(args.output_csv, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(['metric', 'value'])
            writer.writerow(['F1-Score', f1_score])

        print(f"F1-Score Calculation Complete. Result saved to {args.output_csv}")
        print(f"F1-Score: {f1_score:.4f}")

    finally:
        if os.path.exists(tmp_dir):
            shutil.rmtree(tmp_dir)

if __name__ == "__main__":
    main()