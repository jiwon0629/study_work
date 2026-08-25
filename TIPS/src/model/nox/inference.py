import cv2
import numpy as np
from .trt_model import NOX_TRT_Model # 앞서 분석한 TensorRT 모델 로더 클래스를 가져옵니다.
from typing import Optional
from datetime import datetime, timedelta

def nox_predict(
    img_BGR: np.ndarray,      # 입력 이미지 (OpenCV BGR 포맷)
    trt_model: NOX_TRT_Model, # 이미 로드되어 준비된 TensorRT 모델 객체
    ) -> Optional[np.ndarray]:   
    
    # [전처리: 정규화] 
    # 1. 0~255 사이의 정수(uint8) 값을 0~1 사이의 실수(float32) 값으로 변환합니다. 
    #    딥러닝 모델은 일반적으로 작은 실수 범위의 데이터를 입력받아야 연산 정밀도가 높기 때문입니다.
    # 2. np.expand_dims(..., axis=0)를 통해 (H, W, C) 형태의 이미지를 (1, H, W, C) 형태의 배치(Batch) 구조로 만듭니다.
    #    TensorRT 모델은 항상 배치 단위의 입력을 요구하기 때문입니다.
    float_image: np.ndarray = np.expand_dims(np.array(img_BGR, dtype=np.float32) / 255, axis=0)
    
    # 추론에 걸리는 순수 시간을 측정하기 위해 시작 시간을 기록합니다.
    nox_inference_time_now: datetime = datetime.now()
    
    # [추론 수행] 준비된 데이터를 모델에 넣어 결과값을 받아옵니다. 
    # 내부적으로는 GPU 메모리 복사 -> 연산 -> 복사 과정이 일어납니다.
    output_RGB_float: np.ndarray = trt_model.predict(float_image)
    
    # 추론 종료 후 소요 시간을 계산하여 초(seconds) 단위로 저장합니다.
    nox_inference_process_time: timedelta = datetime.now() - nox_inference_time_now
    nox_inference_process_time_seconds = nox_inference_process_time.total_seconds()
    
    # [후처리: 역정규화 및 타입 변환]
    # 1. .squeeze()를 통해 (1, H, W, C) 형태에서 다시 (H, W, C) 형태로 차원을 축소합니다.
    # 2. 다시 255를 곱해 0~1 범위를 0~255 범위의 픽셀 값으로 되돌립니다.
    # 3. .astype(np.int32)를 통해 실수형 데이터를 정수형으로 변환합니다.
    output_RGB_int: np.ndarray = (output_RGB_float.squeeze() * 255).astype(np.int32)
    
    # cv2.convertScaleAbs()를 사용하여 0~255 범위를 벗어난 값을 클리핑(Clipping)하고, 
    # 최종적으로 OpenCV에서 사용할 수 있는 uint8(8비트 무부호 정수) 타입으로 변환합니다.
    output_RGB: np.ndarray = cv2.convertScaleAbs(output_RGB_int)
    
    # 최종 결과 이미지와 추론에 걸린 시간을 함께 반환합니다.
    return output_RGB, nox_inference_process_time_seconds
# 1. float32 / 255를 하는 이유: 신경망은 입력값의 분포가 일정할 때(예: 0~1 사이) 가장 잘 작동합니다. 이를 정규화라고 하며, 모델 학습 시 사용된 방식과 동일하게 입력 데이터를 맞춰줘야 정확한 결과가 나옵니다.
# 2. expand_dims를 하는 이유: AI 모델은 한 장의 이미지뿐만 아니라 수십 장의 이미지를 한 번에 처리(Batch 처리)할 수 있도록 설계되어 있습니다. 따라서 한 장만 넣더라도 "크기가 1인 배치"라는 형식을 맞춰줘야 합니다.
# 3. convertScaleAbs를 하는 이유: 모델 연산 결과로 인해 픽셀 값이 255.1이나 -0.5 같은 값이 나올 수 있습니다. 이를 무시하고 이미지 파일로 저장하면 색상이 깨지므로, 0~255 사이로 값을 강제 조정하고 표준 이미지 타입인 uint8로 변환하는 과정이 필수적입니다.