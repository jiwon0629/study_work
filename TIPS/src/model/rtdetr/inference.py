import cv2
import numpy as np
from .postprocess import postprocess
from .preprocess import preprocess
from .trt_model import RTDETR_TRT_Model
from ultralytics import YOLO
from datetime import datetime, timedelta
from typing import List, Tuple

def rtdetr_predict(
    output_RGB: np.ndarray,
    detect_model: RTDETR_TRT_Model,
    label_list: list,
    detect_model_height: int,
    detect_model_width: int,
    draw_boxes: bool = True,
) -> Tuple[np.ndarray, List, float]:

    allowed_class_ids: list = [0, 2]
    
    if isinstance(detect_model, RTDETR_TRT_Model):
        output_RGB_resized: np.ndarray = cv2.resize(output_RGB, (detect_model_height, detect_model_width))
        pp_image: np.ndarray = preprocess([output_RGB_resized], dtype=np.float32, normalize_factor=255.0, channel_first=True, batched=True)
        scale_factors: np.ndarray = np.array([1.0, 1.0], dtype=np.float32).reshape(1, 2)
        im_shape: np.ndarray = np.array([detect_model_width, detect_model_height], dtype=np.float32).reshape(1, 2)
        
        input_data: dict = {
            'image': pp_image,
            'scale_factor': scale_factors,
            'im_shape': im_shape
        }
        
        rtdetr_inference_time_now: datetime = datetime.now()
        outputs = detect_model.predict(input_data)
        rtdetr_inference_process_time_seconds = (datetime.now() - rtdetr_inference_time_now).total_seconds()
        
        scale_width: float = output_RGB.shape[1] / detect_model_width
        scale_height: float = output_RGB.shape[0] / detect_model_height
        
        postprocess_data: list = postprocess(
            output_data=outputs[1],
            scale_width=scale_width,
            scale_height=scale_height,
            score_threshold=0.4,
            iou_threshold=0.5,
        )
    else:
        # PyTorch YOLO/RT-DETR Model
        rtdetr_inference_time_now: datetime = datetime.now()
        results = detect_model.predict(output_RGB, conf=0.4, iou=0.5, verbose=False)
        rtdetr_inference_process_time_seconds = (datetime.now() - rtdetr_inference_time_now).total_seconds()
        
        # result[0].boxes.data is [x1, y1, x2, y2, conf, cls] in original image scale
        boxes = results[0].boxes.data.cpu().numpy()
        postprocess_data = []
        for box in boxes:
            x1, y1, x2, y2, score, cls = box
            postprocess_data.append([cls, score, x1, y1, x2, y2])

    filtered_postprocess_data = [bbox for bbox in postprocess_data if bbox[0] in allowed_class_ids]

    if draw_boxes:
        for bbox in filtered_postprocess_data:
            class_id, score, x_min, y_min, x_max, y_max = bbox
            class_label: str = label_list[int(class_id)]
            label: str = f"{class_label} {score:.2f}"
            cv2.rectangle(output_RGB, (int(x_min), int(y_min)), (int(x_max), int(y_max)), (255, 0, 255), 2)
            (text_width, text_height), baseline = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 2)
            cv2.rectangle(output_RGB, (int(x_min), int(y_min) - text_height - baseline), (int(x_min) + text_width, int(y_min)), (255, 0, 255), cv2.FILLED)
            cv2.putText(output_RGB, label, (int(x_min), int(y_min) - baseline), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)

    return output_RGB, filtered_postprocess_data, rtdetr_inference_process_time_seconds
