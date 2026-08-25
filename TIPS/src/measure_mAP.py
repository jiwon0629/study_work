# 이 파일은 모델의 탐지 성능을 정량적으로 평가하는 *mAP(mean Average Precision)*를 측정합니다. 특이점은 ultralytics의 내장 검증 기능을 활용하기 위해 임시로 YOLO 데이터셋 형식(.txt 및 .yaml)을 만드는 과정이 포함되어 있다는 것입니다.
import numpy as np
np.bool = bool # 호환성 패치
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
    정답 JSON 파일들을 읽어 YOLO 학습/검증 형식(.txt)과 데이터셋 설정파일(.yaml)로 변환합니다.
    이 과정이 필요한 이유는 ultralytics의 model.val() 함수가 이 형식을 요구하기 때문입니다.
    """
    label_out_dir = Path(tmp_dir) / "labels" / "test"
    label_out_dir.mkdir(parents=True, exist_ok=True)

    image_files = list(Path(image_dir).glob('*.jpg')) + \
                      list(Path(image_dir).glob('*.jpeg')) + \
                      list(Path(image_dir).glob('*.png'))
    
    img_w, img_h = 1920, 1080 # 정규화를 위한 기준 해상도
    class_map = {"Human": 0, "Car": 1} # 클래스 이름 -> ID 매핑
    
    for img_path in image_files:
        label_file = Path(label_dir) / f"{img_path.stem}.json"
        if not label_file.exists():
            continue

        with open(label_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            # JSON 구조에서 어노테이션 리스트를 추출합니다.
            annotations = data.get("Learning_Data_Info.", {}).get("Annotations", [])

        yolo_annots = []
        for ann in annotations:
            cls_id = ann.get("Class_ID")
            if cls_id not in class_map:
                continue
            
            cls_num = class_map[cls_id]
            type_val = ann.get("Type_value", []) # [xmin, ymin, xmax, ymax]
            
            # [YOLO 정규화] 픽셀 좌표를 0~1 사이의 값으로 변환하고 
            # [xmin, ymin, xmax, ymax] -> [center_x, center_y, width, height] 형식으로 변경합니다.
            x_center = (type_val[0] + type_val[2]) / 2 / img_w
            y_center = (type_val[1] + type_val[3]) / 2 / img_h
            width = (type_val[2] - type_val[0]) / img_w
            height = (type_val[3] - type_val[1]) / img_h
            
            yolo_annots.append(f"{cls_num} {x_center:.6f} {y_center:.6f} {width:.6f} {height:.6f}")

        # YOLO 형식의 .txt 파일로 저장합니다.
        with open(label_out_dir / f"{img_path.stem}.txt", 'w') as f:
            f.write("\n".join(yolo_annots))

    # 데이터셋 경로 정보를 담은 .yaml 파일을 생성합니다.
    yaml_content = f"""path: {tmp_dir}
train: images/test
val: images/test
test: images/test 
names:
  0: Human
  1: Car
"""
    
    img_out_dir = Path(tmp_dir) / "images" / "test"
    img_out_dir.mkdir(parents=True, exist_ok=True)
    # 실제 이미지를 복사하는 대신 심볼릭 링크를 생성하여 디스크 공간을 절약합니다.
    for img_path in image_files:
        (img_out_dir / img_path.name).symlink_to(img_path.resolve())

    yaml_path = Path(tmp_dir) / "test_dataset.yaml"
    with open(yaml_path, 'w') as f:
        f.write(yaml_content)
    
    return yaml_path

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model_path", required=True, type=str, help="Path to .pt model file")
    parser.add_argument("--image_dir", default="./ob_testset/inputs/image/", type=str)
    parser.add_argument("--label_dir", default="./ob_testset/inputs/label/", type=str)
    parser.add_argument("--output_csv", default="./ob_testset/map_result.csv", type=str)
    args = parser.parse_args()

    tmp_dir = "/tmp/yolo_val_map"
    if os.path.exists(tmp_dir):
        shutil.rmtree(tmp_dir)

    try:
        # 1. 정답 데이터를 YOLO 형식으로 변환하여 임시 폴더에 저장합니다.
        yaml_path = prepare_yolo_dataset(args.image_dir, args.label_dir, tmp_dir)

        # 2. YOLO 모델을 로드하고 val() 함수를 통해 mAP를 자동으로 계산합니다.
        model = YOLO(args.model_path, task='detect')
        results = model.val(data=str(yaml_path), split='test', plots=False, verbose=False, batch=3)

        # 3. mAP@50 및 mAP@50-95 지표를 추출합니다.
        map50 = results.box.map50
        map50_95 = results.box.map

        # 결과를 CSV 파일로 저장합니다.
        with open(args.output_csv, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(['metric', 'value'])
            writer.writerow(['mAP@50', map50])
            writer.writerow(['mAP@50-95', map50_95])

        print(f"mAP Calculation Complete. Result saved to {args.output_csv}")
        print(f"mAP@50: {map50:.4f}, mAP@50-95: {map50_95:.4f}")

    finally:
        # 작업 완료 후 생성했던 임시 데이터셋 폴더를 삭제합니다.
        if os.path.exists(tmp_dir):
            shutil.rmtree(tmp_dir)

if __name__ == "__main__":
    main()