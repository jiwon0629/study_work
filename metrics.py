import numpy as np
from sklearn.metrics import confusion_matrix, classification_report, accuracy_score
import matplotlib.pyplot as plt
import seaborn as sns

# 1. 테스트 결과 데이터 입력 (예시: 0은 화재 없음, 1은 화재 있음)
# 실제 50장의 정답 (사용자가 직접 확인한 값)
y_true = [1, 1, 0, 1, 0, 0, 1, 1, 0, 0] * 5  # 실제 50장 예시

# 모델이 예측한 값 (결과 폴더의 [Detected]면 1, [Normal]이면 0)
y_pred = [1, 1, 0, 0, 0, 1, 1, 1, 0, 0] * 5  # 모델 예측 예시

# 2. 혼동 행렬(Confusion Matrix) 계산
tn, fp, fn, tp = confusion_matrix(y_true, y_pred).ravel()

# 3. 주요 지표 계산
precision = tp / (tp + fp) if (tp + fp) > 0 else 0
recall = tp / (tp + fn) if (tp + fn) > 0 else 0
accuracy = accuracy_score(y_true, y_pred)

# 4. 결과 출력
print("=== 화재 감지 모델 성능 지표 보고서 ===")
print(f"✅ 정탐(TP): {tp}건 / 정상판단(TN): {tn}건")
print(f"❌ 오탐(FP): {fp}건 / 미탐(FN): {fn}건")
print("-" * 30)
print(f"🎯 정확도 (Accuracy): {accuracy:.2%}")
print(f"🔍 정밀도 (Precision): {precision:.2%}")
print(f"📢 재현율 (Recall): {recall:.2%}") # 군/소방 사업에서 가장 중요!

# 5. 혼동 행렬 시각화 (보고서 삽입용 이미지 생성)
plt.figure(figsize=(8, 6))
cm = confusion_matrix(y_true, y_pred)
sns.heatmap(cm, annot=True, fmt='d', cmap='Blues', 
            xticklabels=['Negative', 'Positive'], 
            yticklabels=['Negative', 'Positive'])
plt.xlabel('Predicted')
plt.ylabel('Actual')
plt.title('Fire Detection Confusion Matrix')
plt.savefig('fire_performance_matrix.png') # 이미지 저장
print("\n📊 'fire_performance_matrix.png'가 저장되었습니다.")