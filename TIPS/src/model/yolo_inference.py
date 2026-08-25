# 이 파일은 ultralytics 라이브러리를 사용하여 YOLO 모델을 로드하고, 객체 탐지를 수행하여 BBox 좌표와 시각화 이미지를 생성합니다.
import cv2
import numpy as np
import time
from ultralytics import YOLO # ultralytics사용(모델 로드)추론
from pathlib import Path

class YOLO_Model:
    def __init__(self, model_path='model1.pt', device='cuda'):
        
        self.model = YOLO(model_path) # ultralytics 사용 (모델 초기화)
        self.model.to(device)

    def predict(self, image, conf=0.25, iou=0.2):
    #  ultralytics의 predict 함수를 사용하여 객체 탐지 수행
    # conf: 신뢰도 임계값, iou: NMS(Non-Maximum Suppression)를 위한 IoU 임계값입니다.

        return self.model.predict(image, conf=conf, iou=iou, imgsz=1080, verbose=False) # ultralytics 사용 (객체 검출)

def yolo_predict(image, model, label_list, width=None, height=None, draw_boxes=False):
    """
    YOLO 모델을 사용하여 이미지를 추론하고, 필요한 데이터(BBox)와 시각화 이미지를 반환하는 함수입니다.
    """
    
    start_time = time.time() # 순수 추론 시간 측정을 위한 시작점
    
    # 모델을 통해 추론을 수행합니다.
    results = model.predict(image)
    inference_time = time.time() - start_time
    
    result = results[0] # 여러 이미지 입력이 가능하므로 첫 번째 결과물을 가져옵니다.
    boxes = result.boxes # 탐지된 모든 BBox 정보를 가져옵니다.
    
    # 관심 대상 클래스 ID (예: 0: Human, 1: Car). 시스템 정의에 따라 필터링합니다.
    TARGET_CLASSES = [0, 1]
    
    postprocess_data = [] # 결과 좌표값들을 저장할 리스트
    output_img = image.copy() # 시각화를 위해 원본 이미지를 복사합니다.
    
    for box in boxes:
        cls = int(box.cls[0]) # 탐지된 객체의 클래스 ID
        
        # 타겟 클래스가 아닌 경우 제외합니다.
        if cls not in TARGET_CLASSES:
            continue
            
        # BBox 좌표(xmin, ymin, xmax, ymax)를 CPU numpy 배열로 변환합니다.
        coords = box.xyxy[0].cpu().numpy()
        conf = float(box.conf[0]) # 탐지 신뢰도(Confidence Score)
        
        # JSON 저장 등에 사용될 표준 딕셔너리 형태로 데이터를 구성합니다.
        det = {
            "class_id": cls,
            "score": conf,
            "bbox": {
                "x_min": float(coords[0]),
                "y_min": float(coords[1]),
                "x_max": float(coords[2]),
                "y_max": float(coords[3])
            }
        }
        postprocess_data.append(det)
        
        # draw_boxes=True인 경우 이미지 위에 BBox와 라벨을 그립니다.
        if draw_boxes:
            label = f"{label_list[cls] if cls < len(label_list) else cls} {conf:.2f}"
            # BBox 사각형 그리기 (초록색, 두께 2)
            cv2.rectangle(output_img, (int(coords[0]), int(coords[1])), (int(coords[2]), int(coords[3])), (0, 255, 0), 2)
            # 클래스 이름과 신뢰도 텍스트 쓰기
            cv2.putText(output_img, label, (int(coords[0]), int(coords[1]) - 10),  
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

    return output_img, postprocess_data, inference_time