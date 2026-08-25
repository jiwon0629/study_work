import os
import cv2
import time

# 경고 메시지 억제
os.environ["CORE_MODEL_SAM_ENABLED"] = "False"
os.environ["CORE_MODEL_GAZE_ENABLED"] = "False"

from inference import get_model
from sklearn.metrics import confusion_matrix, accuracy_score

# 1. 설정 및 경로 (경로를 "images"로 고정했습니다)
API_KEY = "oW8rdeGMl2lkZQBAibtV"
MODEL_ID = "fire-detection-yolo-1gn9t/2"
IMAGE_DIR = "data/images"  
SAVE_DIR = "results/yolov8/fire-detection-yolo-1gn9t"
os.makedirs(SAVE_DIR, exist_ok=True)

# 2. 모델 로드
print("Roboflow API 모델 로드 중...")
model = get_model(model_id=MODEL_ID, api_key=API_KEY)

def get_actual(name):
    keywords = ['fire', 'smoke', 'burn', 'flame', 'fire_']
    return 1 if any(k in name.lower() for k in keywords) else 0

y_true, y_pred = [], []
total_pure_inference_time = 0
test_start_full = time.time()

# 3. 테스트 시작
if not os.path.exists(IMAGE_DIR):
    print(f"오류: '{IMAGE_DIR}' 폴더가 없습니다.")
    exit()

img_list = sorted([f for f in os.listdir(IMAGE_DIR) if f.lower().endswith(('.jpg', '.jpeg', '.png'))])
print(f"테스트 시작: 총 {len(img_list)}매")

for img_name in img_list:
    img_path = os.path.join(IMAGE_DIR, img_name)
    actual = get_actual(img_name)
    y_true.append(actual)

    try:
        # --- 순수 추론 시간 측정 (API 호출) ---
        start_time = time.time()
        results = model.infer(img_path)
        end_time = time.time()
        
        duration = end_time - start_time
        total_pure_inference_time += duration
        
        predictions = results[0].predictions
        predicted = 1 if len(predictions) > 0 else 0
        y_pred.append(predicted)

        status = "SUCCESS" if actual == predicted else "FAIL"
        print(f"[{status}] {img_name} | {duration*1000:.2f}ms")

        # 결과 이미지 시각화 및 저장
        image = cv2.imread(img_path)
        if predicted == 1:
            for p in predictions:
                x1, y1 = int(p.x - p.width / 2), int(p.y - p.height / 2)
                x2, y2 = int(p.x + p.width / 2), int(p.y + p.height / 2)
                cv2.rectangle(image, (x1, y1), (x2, y2), (0, 255, 0), 2)
        cv2.imwrite(os.path.join(SAVE_DIR, f"res_{img_name}"), image)

    except Exception as e:
        print(f"오류 발생 ({img_name}): {e}")

# --- 4. 최종 지표 계산 (에러 방지를 위해 변수로 미리 계산) ---
total_elapsed_full = time.time() - test_start_full
avg_inf = (total_pure_inference_time / len(img_list)) * 1000 if img_list else 0

# 혼동 행렬 지표
tn, fp, fn, tp = confusion_matrix(y_true, y_pred, labels=[0, 1]).ravel()
acc = accuracy_score(y_true, y_pred)
recall = tp / (tp + fn) if (tp + fn) > 0 else 0
precision = tp / (tp + fp) if (tp + fp) > 0 else 0

# 최종 요약 출력 (포맷팅 오류 해결 버전)
summary = f"""
============================================================
[YOLOv8 API 성능 및 시간 분석 요약]
============================================================
* 모델 ID: {MODEL_ID}
* 테스트 데이터 수량: 총 {len(y_true)}매
------------------------------------------------------------
* 모델 추론 총 소요시간: {total_pure_inference_time:.2f}초 (API 전송 포함)
* 평균 추론 속도(장당): {avg_inf:.2f}ms
* 시스템 전체 실행시간: {total_elapsed_full:.2f}초
------------------------------------------------------------
1. 정탐(TP): {tp:2d} | 2. 정상(TN): {tn:2d}
3. 오탐(FP): {fp:2d} | 4. 미탐(FN): {fn:2d}
------------------------------------------------------------
- 정확도(Accuracy) : {acc:.2%}
- 정밀도(Precision): {precision:.2%}
- 재현율(Recall)   : {recall:.2%}
============================================================
"""
# 리포트 저장
with open(os.path.join(SAVE_DIR, "detailed_report.txt"), "w", encoding="utf-8") as f:
    f.write(summary)
print(summary)
