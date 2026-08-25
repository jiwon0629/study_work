import torch
import numpy as np
from typing import List, Union

def iou(boxA: torch.Tensor, boxB: torch.Tensor) -> torch.Tensor:
    xA = torch.max(boxA[:, None, 0], boxB[None, :, 0])
    yA = torch.max(boxA[:, None, 1], boxB[None, :, 1])
    xB = torch.min(boxA[:, None, 2], boxB[None, :, 2])
    yB = torch.min(boxA[:, None, 3], boxB[None, :, 3])

    interArea = torch.clamp(xB - xA, min=0) * torch.clamp(yB - yA, min=0)
    boxAArea = (boxA[:, 2] - boxA[:, 0]) * (boxA[:, 3] - boxA[:, 1])
    boxBArea = (boxB[:, 2] - boxB[:, 0]) * (boxB[:, 3] - boxB[:, 1])

    iou = interArea / (boxAArea[:, None] + boxBArea[None, :] - interArea)
    return iou

def nms(
    detections: Union[np.ndarray, torch.Tensor],
    score_threshold: float = 0.5,
    iou_threshold: float = 0.5) -> List[List[float]]:
    
    if isinstance(detections, np.ndarray):
        detections = torch.from_numpy(detections).float()
        
    scores: torch.Tensor = detections[:, 1]
    keep: torch.Tensor = scores >= score_threshold
    detections: torch.Tensor = detections[keep]
    scores: torch.Tensor = detections[:, 1]
    boxes: torch.Tensor = detections[:, 2:]

    idxs: torch.Tensor = torch.argsort(scores, descending=True)
    selected_idxs: List[int] = []

    while idxs.numel() > 0:
        current_idx: int = idxs[0].item()
        selected_idxs.append(current_idx)

        if idxs.numel() == 1:
            break

        current_box: torch.Tensor = boxes[current_idx].unsqueeze(0)
        rest_boxes: torch.Tensor = boxes[idxs[1:]]
        ious: torch.Tensor = iou(current_box, rest_boxes).squeeze()

        idxs = idxs[1:][ious < iou_threshold]

    return detections[selected_idxs].tolist()
