from typing import List, Union
import numpy as np
from .iou import nms
import torch

def postprocess(
    output_data: Union[np.ndarray, torch.Tensor],
    scale_width: float,
    scale_height: float,
    score_threshold: float = 0.5,
    iou_threshold: float = 0.5) -> List[List[float]]:
    
    nms_results: List[List[float]] = nms(output_data, score_threshold=score_threshold, iou_threshold=iou_threshold)

    scaled_bboxes: List[List[float]] = []
    for bbox in nms_results:
        class_id, score, x_min, y_min, x_max, y_max = bbox
        new_x_min: float = x_min * scale_width
        new_y_min: float = y_min * scale_height
        new_x_max: float = x_max * scale_width
        new_y_max: float = y_max * scale_height
        scaled_bbox: List[float] = [class_id, score, new_x_min, new_y_min, new_x_max, new_y_max]
        scaled_bboxes.append(scaled_bbox)
    
    return scaled_bboxes
