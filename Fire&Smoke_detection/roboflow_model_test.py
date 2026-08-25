
# roboflow model test
from inference import get_model

# 내 roboflow api key
API_KEY = "oW8rdeGMl2lkZQBAibtV"
# 테스트해 볼 모델 ID (클래스가 분리된 모델)
MODEL_ID = "fire-detection-yolo-1gn9t/2" 

model = get_model(model_id=MODEL_ID, api_key=API_KEY)

# 여기서 [0: 'fire', 1: 'smoke'] 처럼 나오는지 확인
print("모델의 클래스 구성:", model.class_names)
