from typing import List, Tuple, Dict, Any
import torch
import numpy as np
from model.rtdetr import iou

# ================================================================= #
#                  mAP (mean Average Precision) 계산 함수             #
# ================================================================= #
def mAP_calculate(
    answer_list: List[Tuple[int, List[int]]],
    result_data: List[List[float]],
    iou_threshold: float = 0.5,
) -> float:
    """
    하나의 이미지에 대한 mAP (mean Average Precision)를 계산합니다.
    """
    # 클래스별로 정답과 예측 데이터를 그룹화합니다.
    result_class = {}
    for pred in result_data:
        class_id, score, x_min, y_min, x_max, y_max = pred
        if class_id not in result_class:
            result_class[class_id] = []
        result_class[class_id].append((score, [x_min, y_min, x_max, y_max]))

    answer_class = {}
    for gt in answer_list:
        class_id, box = gt
        if class_id not in answer_class:
            answer_class[class_id] = []
        answer_class[class_id].append(box)

    average_precisions = []
    
    # 각 클래스에 대해 AP(Average Precision)를 계산합니다.
    for class_id in answer_class:
        gt_boxes = torch.tensor(answer_class[class_id], dtype=torch.float32)
        pred_boxes = result_class.get(class_id, [])
        # 신뢰도 점수가 높은 순으로 예측을 정렬합니다.
        pred_boxes = sorted(pred_boxes, key=lambda x: x[0], reverse=True)

        if not pred_boxes:
            average_precisions.append(0.0)
            continue

        pred_boxes = torch.tensor([b[1] for b in pred_boxes], dtype=torch.float32)

        ious = iou(pred_boxes, gt_boxes)

        tp = torch.zeros(pred_boxes.shape[0])
        fp = torch.zeros(pred_boxes.shape[0])
        matched_gt_boxes = set()

        # IoU 기반으로 TP, FP를 판정합니다.
        for i in range(pred_boxes.shape[0]):
            iou_vals = ious[i]
            max_iou, max_iou_idx = torch.max(iou_vals, dim=0)

            if max_iou >= iou_threshold and max_iou_idx.item() not in matched_gt_boxes:
                tp[i] = 1
                matched_gt_boxes.add(max_iou_idx.item())
            else:
                fp[i] = 1

        # 정밀도-재현율 곡선을 계산하여 AP를 구합니다.
        tp_cumsum = torch.cumsum(tp, dim=0)
        fp_cumsum = torch.cumsum(fp, dim=0)

        precision = tp_cumsum / (tp_cumsum + fp_cumsum + 1e-6)
        recall = tp_cumsum / len(gt_boxes)

        precision = precision.numpy()
        recall = recall.numpy()
        recall_thresholds = np.linspace(0, 1, 101)
        precisions = np.zeros_like(recall_thresholds)
        for i, t in enumerate(recall_thresholds):
            precisions[i] = np.max(precision[recall >= t]) if np.any(recall >= t) else 0
        
        average_precision = np.mean(precisions)
        average_precisions.append(average_precision)

    # 모든 클래스의 AP 평균을 내어 mAP를 계산합니다.
    mAP = sum(average_precisions) / len(average_precisions) if average_precisions else 0
    return mAP


# ================================================================= #
#                       F1-Score 계산 관련 함수                      #
# ================================================================= #
def calculate_f1_score_components(
    answer_list: List[Tuple[int, List[int]]],
    result_data: List[List[float]],
    iou_threshold: float = 0.5,
    confidence_threshold: float = 0.5
) -> Tuple[int, int, int]:
    """
    하나의 이미지에 대한 TP, FP, FN 개수를 계산하여 반환합니다.
    F1-Score는 이 값들을 전체 데이터셋에 대해 합산한 뒤 계산합니다.
    """
    
    # 1. 지정된 신뢰도 임계값(confidence_threshold) 미만의 예측을 모두 제거합니다.
    predictions = [pred for pred in result_data if pred[1] >= confidence_threshold]
    
    if not predictions:
        # 예측이 하나도 없으면, 모든 정답이 '못 찾은 정답(FN)'이 됩니다.
        return 0, 0, len(answer_list)
        
    if not answer_list:
        # 정답이 하나도 없으면, 모든 예측이 '오탐(FP)'이 됩니다.
        return 0, len(predictions), 0

    gt_boxes = torch.tensor([gt[1] for gt in answer_list], dtype=torch.float32)
    pred_boxes = torch.tensor([p[2:] for p in predictions], dtype=torch.float32)

    # 2. IoU를 계산하여 예측과 정답을 매칭합니다.
    ious = iou(pred_boxes, gt_boxes)
    matched_gt_boxes = set()
    tp = 0
    
    for i in range(len(predictions)):
        pred_class = predictions[i][0]  # 예측 클래스 ID
        iou_vals = ious[i]
        # 각 예측에 대해 가장 IoU가 높은 정답을 찾습니다.
        max_iou, max_iou_idx = torch.max(iou_vals, dim=0)
        gt_class = answer_list[max_iou_idx.item()][0]  # GT 클래스 ID

        # IoU가 임계값 이상이고, 클래스가 일치하며, 아직 다른 예측과 매칭되지 않은 정답이라면 TP(True Positive)입니다.
        if max_iou >= iou_threshold and max_iou_idx.item() not in matched_gt_boxes and pred_class == gt_class:
            tp += 1
            matched_gt_boxes.add(max_iou_idx.item())

    # 3. TP, FP, FN 값을 최종 계산합니다.
    fp = len(predictions) - tp  # FP = 전체 예측 수 - TP
    fn = len(answer_list) - tp    # FN = 전체 정답 수 - TP
    
    return tp, fp, fn