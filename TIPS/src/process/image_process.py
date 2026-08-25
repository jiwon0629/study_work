# 이 파일은 이미지 로드 -> 화질 개선(NOX) -> 객체 탐지(RT-DETR/YOLO) -> 결과 저장의 선형적인 흐름을 처리합니다.
# 이미지 한 장에 대해 화질 개선과 객체 탐지를 수행하고 결과를 저장하는 메인 프로세스
import os
from pathlib import Path
import cv2
import yaml
from datetime import datetime, timedelta
import numpy as np
from typing import List
import json
from utils import save_process_time, save_to_json, answer_json_load, mAP_calculate, image_metadata
from model.rtdetr import rtdetr_predict, RTDETR_TRT_Model
from ultralytics import YOLO
from model.nox import nox_predict, NOX_TRT_Model
from model.yolo_inference import YOLO_Model, yolo_predict

def image_process(
    ini_dict: dict,      # 전체 설정 값
    input_path: Path,    # 처리할 이미지 경로
    input_dir: Path,     # 입력 루트 경로
    result_dir: Path,    # 결과 저장 루트 경로
    nox_apply: bool,     # NOX 화질 개선 적용 여부
    rtdetr_apply: bool,  # RT-DETR 탐지 적용 여부
    yolo_apply: bool,    # YOLO 탐지 적용 여부
    save_csv: bool,      # 처리 시간 기록 여부
    concat_apply: bool,  # 결과 이미지 병합 여부
    mAP: bool,           # 정확도(mAP) 계산 여부
    mAP_path: Path = None,
    mAP_List: List[float] = None,
    nox_model=None,      # 미리 로드된 NOX 모델 객체
    yolo_model=None,     # 미리 로드된 YOLO 모델 객체
    nox_width=640,       
    nox_height=640       
) -> List[float]:

    # [경로 유지] 입력 폴더의 하위 구조(서브폴더)를 결과 폴더에서도 그대로 유지하기 위해 상대 경로를 계산합니다.
    relative_path = input_path.relative_to(input_dir)
    
    # 설정 파일에서 모델의 입력 크기 및 GPU 설정을 가져옵니다. 이는 모델마다 요구하는 입력 규격이 다르기 때문입니다.
    rtdetr_model_path: str = ini_dict['RTDETR']['RTDETR_MODEL_PATH']
    config_path: str = ini_dict['RTDETR']['CONFIG_PATH']
    detect_model_height: int = ini_dict['RTDETR']['RTDETR_MODEL_HEIGHT']
    detect_model_width: int = ini_dict['RTDETR']['RTDETR_MODEL_WIDTH']
    gpu: int = ini_dict['CONFIG']['GPU']
    json_path: str = ini_dict['CONFIG']['JSON_PATH']

    # 모델이 예측한 클래스 번호를 실제 이름(예: 'Person', 'Car')으로 바꾸기 위해 라벨 리스트를 로드합니다.
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
    label_list = config['label_list'] 

    now_time: datetime = datetime.now() # 전체 프로세스 소요 시간 측정을 위한 시작점
    
    # [전처리] utils.image_metadata를 통해 이미지를 BGR 형태로 읽어오고 기본 정보를 획득합니다.
    img_BGR, _, _ = image_metadata(input_path, ini_dict)
    orig_img_h, orig_img_w = img_BGR.shape[:2] # 나중에 복원하기 위해 원본 크기를 저장합니다.
    
    # [크기 조정] NOX 모델은 고정된 입력 크기를 요구하므로 리사이즈가 필요합니다.
    resized_img_BGR = cv2.resize(img_BGR, (nox_width, nox_height))
    
    nox_inference_process_time = 0.0 
    det_inference_process_time = 0.0 

    # --- 단계 1: 이미지 화질 개선 (NOX) ---
    if nox_apply and nox_model is not None:
        # 저화질 이미지를 고화질로 복원합니다. 이는 이후 단계의 객체 탐지 정확도를 높이기 위함입니다.
        output_RGB, nox_inference_process_time_seconds = nox_predict(resized_img_BGR, nox_model)
        nox_inference_process_time = nox_inference_process_time_seconds
        
        # 모델 출력물을 다시 원본 크기로 되돌려 사용자가 원본과 비교할 수 있게 합니다.
        output_RGB = cv2.resize(output_RGB, (orig_img_w, orig_img_h))
        
        # 개선된 이미지만 따로 저장하여 화질 개선 효과를 확인할 수 있게 합니다.
        nox_output_path = result_dir / "nox" / relative_path.parent / (relative_path.stem + "_NOX.jpg")
        os.makedirs(nox_output_path.parent, exist_ok=True)
        cv2.imwrite(str(nox_output_path), output_RGB)
    else:
        # 화질 개선을 건너뛰면 그대로 원본 이미지를 다음 단계(탐지)로 넘깁니다.
        output_RGB = img_BGR 

    postprocess_data = [] 
    
    # --- 단계 2: 객체 탐지 (RT-DETR 또는 YOLO) ---
    if rtdetr_apply:
        # RT-DETR 모델 설정: .pt(PyTorch) 파일이면 YOLO 클래스로, 아니면 TensorRT 가속 모델로 로드합니다.
        if rtdetr_model_path.endswith('.pt'):
            detect_model = YOLO(rtdetr_model_path, task='detect')
        else:
            detect_model = RTDETR_TRT_Model(gpu=gpu, model_path=rtdetr_model_path, 
                                           input_shape=(1, 3, detect_model_width, detect_model_height), datatype=np.float32)
        
        # [데이터 획득] 시각화 없이 BBox 좌표값만 빠르게 가져옵니다 (draw_boxes=False).
        output_RGB_clean, postprocess_data, rtdetr_time = rtdetr_predict(output_RGB.copy(), detect_model, label_list, detect_model_width, detect_model_height, draw_boxes=False)
        det_inference_process_time = rtdetr_time
        
        # [타입 변환] numpy float32는 json.dump에서 에러가 나므로, 파이썬 기본 float으로 변환합니다.
        postprocess_data = [[float(x) if isinstance(x, (np.float32, np.float64)) else x for x in bbox] for bbox in postprocess_data if isinstance(bbox, (list, tuple))] if postprocess_data and not isinstance(postprocess_data[0], dict) else postprocess_data
        
        # [결과 저장] 탐지된 좌표 정보를 JSON 파일로 저장하여 추후 분석이나 mAP 계산에 사용합니다.
        json_output_path = result_dir / "labels" / relative_path.parent / (input_path.stem + ".json")
        os.makedirs(json_output_path.parent, exist_ok=True)
        with open(json_output_path, 'w') as f:
            json.dump({"input_path": str(input_path), "image_name": input_path.name, "detections": postprocess_data, "detection_count": len(postprocess_data), "inference_time": rtdetr_time}, f, indent=2)
        
        # [시각화] 실제 이미지 위에 BBox를 그려서 사람이 눈으로 확인할 수 있는 결과물을 만듭니다.
        nox_with_boxes, _, _ = rtdetr_predict(output_RGB.copy(), detect_model, label_list, detect_model_width, detect_model_height, draw_boxes=True)
        bbox_output_path = result_dir / "detections" / relative_path.parent / (input_path.stem + "_detected.jpg")
        os.makedirs(bbox_output_path.parent, exist_ok=True)
        cv2.imwrite(str(bbox_output_path), nox_with_boxes)

    elif yolo_apply and yolo_model is not None:
        # YOLO 모델을 사용할 경우 RT-DETR과 동일한 프로세스(추론 -> JSON저장 -> 시각화저장)를 수행합니다.
        output_RGB_yolo, postprocess_data, yolo_time = yolo_predict(output_RGB.copy(), yolo_model, label_list, draw_boxes=False)
        det_inference_process_time = yolo_time
        
        postprocess_data = [[float(x) if isinstance(x, (np.float32, np.float64)) else x for x in bbox] for bbox in postprocess_data if isinstance(bbox, (list, tuple))] if postprocess_data and not isinstance(postprocess_data[0], dict) else postprocess_data
        
        json_output_path = result_dir / "labels" / relative_path.parent / (input_path.stem + ".json")
        os.makedirs(json_output_path.parent, exist_ok=True)
        with open(json_output_path, 'w') as f:
            json.dump({"input_path": str(input_path), "image_name": input_path.name, "detections": postprocess_data, "detection_count": len(postprocess_data), "inference_time": yolo_time}, f, indent=2)
        
        nox_with_boxes, _, _ = yolo_predict(output_RGB.copy(), yolo_model, label_list, draw_boxes=True)
        bbox_output_path = result_dir / "detections" / relative_path.parent / (input_path.stem + "_detected.jpg")
        os.makedirs(bbox_output_path.parent, exist_ok=True)
        cv2.imwrite(str(bbox_output_path), nox_with_boxes)

    # 총 AI 추론 시간(화질개선 + 탐지)을 계산합니다.
    AI_Inference_process_time = nox_inference_process_time + det_inference_process_time
    AI_Inference_process_time_seconds = f"{AI_Inference_process_time:.2f}"
    
    # --- 단계 3: 정확도 측정 (mAP) ---
    mAP_value = None
    if mAP:
        # 정답 데이터(Ground Truth)를 로드하고, 모델이 예측한 값과 비교하여 정확도를 계산합니다.
        answer_data = answer_json_load(input_path.name, mAP_path)
        if len(postprocess_data) > 0 and isinstance(postprocess_data[0], dict):
            # 데이터 포맷이 딕셔너리 형태인 경우 튜플 형태로 변환하여 계산 함수에 전달합니다.
            old_format_data = [(det['class_id'], det['score'], det['bbox']['x_min'], det['bbox']['y_min'], det['bbox']['x_max'], det['bbox']['y_max']) for det in postprocess_data]
            mAP_value = mAP_calculate(answer_data, old_format_data)
        else:
            mAP_value = mAP_calculate(answer_data, postprocess_data)
        if mAP_List is not None:
            mAP_List.append(mAP_value)

    # [최종 결과 통합] 모든 탐지 데이터를 표준 포맷으로 정리하여 최종 JSON 파일에 기록합니다.
    if len(postprocess_data) > 0 and isinstance(postprocess_data[0], dict):
        json_data = [(det['class_id'], det['score'], det['bbox']['x_min'], det['bbox']['y_min'], det['bbox']['x_max'], det['bbox']['y_max']) for det in postprocess_data]
    elif len(postprocess_data) > 0 and isinstance(postprocess_data[0], (list, tuple)):
        json_data = postprocess_data
    else:
        json_data = postprocess_data
    save_to_json(label_list, str(input_path), json_data, json_path, str(AI_Inference_process_time_seconds))

    # [성능 기록] CSV 파일에 파일별 처리 시간을 기록하여 전체적인 성능 벤치마크를 수행할 수 있게 합니다.
    if save_csv:
        process_time: str = str(datetime.now() - now_time)
        save_process_time(save_csv, str(input_path), str(bbox_output_path), process_time)

    return mAP_List