import os
import cv2
import time
import torch
import numpy as np
from ultralytics import YOLO
from sklearn.metrics import confusion_matrix, accuracy_score

# 1. 설정 및 경로
MODEL_PATH = "YOLOv10-FireSmoke-X.pt"
IMAGE_DIR = "data//images"
SAVE_DIR = "results/yolov10/YOLOv10-FireSmoke-X"
os.makedirs(SAVE_DIR, exist_ok=True)

# 2. 모델 로드 및 GPU 설정
device = '0' if torch.cuda.is_available() else 'cpu'
model = YOLO(MODEL_PATH)

print("-" * 50)
print(f"시스템 시작: {time.strftime('%Y-%m-%d %H:%M:%S')}")
print(f"분석 장치: {'NVIDIA GPU (CUDA)' if device == '0' else 'CPU'}")
print(f"대상 클래스: {model.names}")
print("-" * 50)

def get_actual(name):
    keywords = ['fire', 'smoke', 'burn', 'flame', 'fire_']
    return 1 if any(k in name.lower() for k in keywords) else 0

y_true, y_pred = [], []
total_pure_inference_time = 0  # 순수 추론 시간만 합칠 변수
test_start_full = time.time()  # 시스템 전체 시작 시간

# 3. 분석 실행
img_list = sorted([f for f in os.listdir(IMAGE_DIR) if f.lower().endswith(('.jpg', '.jpeg', '.png'))])

for img_name in img_list:
    img_path = os.path.join(IMAGE_DIR, img_name)
    actual = get_actual(img_name)
    y_true.append(actual)

    try:
        # --- 순수 추론 시간 측정 시작 ---
        start_time = time.time()
        results = model.predict(source=img_path, conf=0.6, classes=[0, 1], save=False, device=device, verbose=False)
        end_time = time.time()
        # ----------------------------
        
        duration = end_time - start_time
        total_pure_inference_time += duration # 순수 시간 누적
        proc_time_ms = duration * 1000
        
        result = results[0]
        predicted = 1 if len(result.boxes) > 0 else 0
        y_pred.append(predicted)

        status_text = "[SUCCESS]" if actual == predicted else "[FAIL]"
        print(f"{status_text} {img_name} | {proc_time_ms:.2f}ms")

        # 이미지 저장 (이 작업은 순수 추론 시간 측정에서 제외됨)
        cv2.imwrite(os.path.join(SAVE_DIR, f"res_{img_name}"), result.plot())

    except Exception as e:
        print(f"오류 발생 ({img_name}): {e}")

# 4. 최종 지표 산출
total_elapsed_full = time.time() - test_start_full
avg_inference_time = (total_pure_inference_time / len(img_list)) * 1000

tn, fp, fn, tp = confusion_matrix(y_true, y_pred, labels=[0, 1]).ravel()
acc = accuracy_score(y_true, y_pred)
precision = tp / (tp + fp) if (tp + fp) > 0 else 0
recall = tp / (tp + fn) if (tp + fn) > 0 else 0

summary = f"""
============================================================
[최종 성능 및 시간 분석 요약 (기준: 순수 추론)]
============================================================
* 모델명: {MODEL_PATH}
* 테스트 데이터 수량: 총 {len(y_true)}매
------------------------------------------------------------
* 모델 추론 총 소요시간: {total_pure_inference_time:.2f}초 (이전 9초 기준과 동일)
* 평균 추론 속도(장당): {avg_inference_time:.2f}ms
* 시스템 전체 실행시간: {total_elapsed_full:.2f}초 (파일저장 포함)
------------------------------------------------------------
1. 정탐(TP): {tp:2d} | 2. 정상(TN): {tn:2d}
3. 오탐(FP): {fp:2d} | 4. 미탐(FN): {fn:2d}
------------------------------------------------------------
- 정확도(Accuracy) : {acc:.2%}
- 정밀도(Precision): {precision:.2%}
- 재현율(Recall)   : {recall:.2%}
============================================================
"""
with open(os.path.join(SAVE_DIR, "detailed_performance_report.txt"), "w", encoding="utf-8") as f:
    f.write(summary)
print(summary)
