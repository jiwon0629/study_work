"""
임시 검증용 스크립트

RT-DETR TensorRT 엔진 문제(GPU 아키텍처 불일치)가 해결되기 전까지,
객체탐지만 YOLO(ultralytics)로 대체하고 PAR/ReID/MoveNet 파이프라인이
정상 동작하는지 먼저 검증하기 위한 스크립트입니다.

경로는 아래 트리 구조 기준으로 맞췄습니다 (VS Code 스크린샷 기준):
  model_test(PAR_ReID_OD)/
    elements/object_detection/reid/analyzer/service.py   <- analyze_patch, OnnxModels, QdrantAdapter
    model_repository/movenet/model.onnx
    model_repository/reid/pass_transreid_vit_small.onnx
    model_repository/par/promptpar_pa100k.onnx (+ .onnx.data)
    model_repository/par/pa100k_attributes.txt

ELEMENTS_BASE, VIDEO_PATH 등 실제 경로가 다르면 아래 상수만 수정하면 됩니다.
"""
import json, sys, tempfile, time, os
from pathlib import Path

os.environ["CUDA_VISIBLE_DEVICES"] = ""

# 실제 프로젝트 루트 경로로 수정하세요.
ELEMENTS_BASE = "/home/dev/workspace/model_test(PAR_ReID_OD)"

# reid 패키지가 elements 밑에 있으므로 이 경로를 sys.path에 추가.
sys.path.insert(0, f"{ELEMENTS_BASE}/elements")

import cv2
import numpy as np
from ultralytics import YOLO
from qdrant_client import QdrantClient
from qdrant_client.http import models as rest
from reid.analyzer.service import OnnxModels, QdrantAdapter, analyze_patch

# ─── Configuration ─────────────────────────────────────────────
# 검증용 테스트 영상 경로로 수정하세요.
VIDEO_PATH = f"{ELEMENTS_BASE}/test_images/sample.avi"
OUTPUT_VIDEO_PATH = f"{ELEMENTS_BASE}/test_images/sample_output.avi"
RESULTS_JSON_PATH = f"{ELEMENTS_BASE}/test_images/results_video.json"

YOLO_CONF_THRESH = 0.5
YOLO_IOU_THRESH = 0.5
IOU_TRACK_MATCH_THRESH = 0.3
MAX_LOST_FRAMES = 15
FRAME_SKIP = 0

config = {
    "t_match": 0.6, "t_new": 0.3, "score_direction": "higher",
    "embed_dim": 768,
    "pose_threshold_default": 0.15, "pose_threshold_hip": 0.15, "pose_threshold_distal": 0.05,
    "prototype_max_per_person": 16, "prototype_search_k": 24, "prototype_person_score_top_n": 3,
    "prototype_min_quality": 0.55, "prototype_min_margin": 0.03,
    "prototype_min_interval_sec": 1.0, "prototype_similarity_redundancy_threshold": 0.97,
    "prototype_eviction_policy": "lowest_quality_then_oldest",
    "quality_pose_weight": 0.30, "quality_sharpness_weight": 0.50, "quality_margin_weight": 0.20,
    "quality_sharpness_ref": 120.0,
}

# ─── Qdrant (in-memory) ───────────────────────────────────────
client = QdrantClient(location=":memory:")
for name in ["person_embeddings", "person_profiles"]:
    client.create_collection(
        collection_name=name,
        vectors_config=rest.VectorParams(size=768, distance=rest.Distance.COSINE),
    )
qdrant = QdrantAdapter(client, "person_embeddings", "person_profiles", rest)

# ─── Models (PAR / ReID / MoveNet) ─────────────────────────────
models = OnnxModels(
    movenet_path=Path(f"{ELEMENTS_BASE}/model_repository/movenet/model.onnx"),
    reid_path=Path(f"{ELEMENTS_BASE}/model_repository/reid/pass_transreid_vit_small.onnx"),
    promptpar_path=Path(f"{ELEMENTS_BASE}/model_repository/par/promptpar_pa100k.onnx"),
    promptpar_attributes=Path(f"{ELEMENTS_BASE}/model_repository/par/pa100k_attributes.txt"),
    pose_threshold_default=0.15,
    pose_threshold_hip=0.15,
    pose_threshold_distal=0.05,
)
config["embed_dim"] = models.embed_dim

# ─── 객체 탐지: YOLO (RT-DETR 대신 임시로 검증용) ─────────────────
# 로컬에 yolov8n.pt가 없으면 ultralytics가 인터넷에서 자동 다운로드합니다.
yolo = YOLO("yolo26n.pt", task="detect")


# ─── IoU Tracker ──────────────────────────────────────────────
class Track:
    def __init__(self, track_id, bbox, frame_idx):
        self.track_id = track_id
        self.bbox = bbox
        self.last_frame = frame_idx
        self.lost_count = 0
        self.color = tuple(np.random.randint(0, 255, 3).tolist())

class SimpleTracker:
    def __init__(self, iou_threshold=0.3, max_lost=15):
        self.tracks = []
        self.next_id = 1
        self.iou_threshold = iou_threshold
        self.max_lost = max_lost

    def update(self, detections, frame_idx):
        matched = [False] * len(detections)
        for track in self.tracks:
            if track.lost_count > self.max_lost:
                continue
            best_iou = 0
            best_idx = -1
            for i, (dbox, _) in enumerate(detections):
                if matched[i]:
                    continue
                iou = self._iou(track.bbox, dbox)
                if iou > best_iou:
                    best_iou = iou
                    best_idx = i
            if best_iou >= self.iou_threshold:
                track.bbox = detections[best_idx][0]
                track.last_frame = frame_idx
                track.lost_count = 0
                matched[best_idx] = True

        for track in self.tracks:
            if track.last_frame < frame_idx:
                track.lost_count += 1

        for i, (bbox, _) in enumerate(detections):
            if not matched[i]:
                self.tracks.append(Track(self.next_id, bbox, frame_idx))
                self.next_id += 1

        self.tracks = [t for t in self.tracks if t.lost_count <= self.max_lost]

    def active_tracks(self):
        return [(t.track_id, t.bbox, t.color) for t in self.tracks if t.lost_count == 0]

    @staticmethod
    def _iou(box_a, box_b):
        x1 = max(box_a[0], box_b[0])
        y1 = max(box_a[1], box_b[1])
        x2 = min(box_a[2], box_b[2])
        y2 = min(box_a[3], box_b[3])
        inter = max(0, x2 - x1) * max(0, y2 - y1)
        area_a = (box_a[2] - box_a[0]) * (box_a[3] - box_a[1])
        area_b = (box_b[2] - box_b[0]) * (box_b[3] - box_b[1])
        union = area_a + area_b - inter
        return inter / union if union > 0 else 0


# ─── Video Processing ─────────────────────────────────────────
cap = cv2.VideoCapture(VIDEO_PATH)
if not cap.isOpened():
    raise RuntimeError(f"영상을 열 수 없습니다: {VIDEO_PATH} (VIDEO_PATH 경로를 확인하세요)")

fps = cap.get(cv2.CAP_PROP_FPS)
width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

os.makedirs(os.path.dirname(OUTPUT_VIDEO_PATH), exist_ok=True)
fourcc = cv2.VideoWriter_fourcc(*"XVID")
out = cv2.VideoWriter(OUTPUT_VIDEO_PATH, fourcc, fps, (width, height))

tracker = SimpleTracker(iou_threshold=IOU_TRACK_MATCH_THRESH, max_lost=MAX_LOST_FRAMES)

all_results = []
frame_idx = 0
total_processed = 0
t_start = time.time()

print(f"Input : {VIDEO_PATH}")
print(f"Output: {OUTPUT_VIDEO_PATH}")
print(f"Frames: {total_frames}, Resolution: {width}x{height}, FPS: {fps}")
print("-" * 70)

while True:
    ret, frame = cap.read()
    if not ret:
        break

    if FRAME_SKIP > 0 and frame_idx % (FRAME_SKIP + 1) != 0:
        frame_idx += 1
        continue

    results = yolo(frame, classes=[0], conf=YOLO_CONF_THRESH, iou=YOLO_IOU_THRESH, verbose=False)

    detections = []
    for r in results:
        if r.boxes is None:
            continue
        for box in r.boxes:
            bbox = box.xyxy[0].tolist()
            conf = float(box.conf)
            detections.append((bbox, conf))

    tracker.update(detections, frame_idx)

    frame_results = []
    for track_id, bbox, color in tracker.active_tracks():
        x1, y1, x2, y2 = map(int, bbox)
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(width - 1, x2), min(height - 1, y2)
        if x2 <= x1 or y2 <= y1:
            continue

        patch = frame[y1:y2, x1:x2]
        if patch.size == 0:
            continue

        tmp = Path(tempfile.mktemp(suffix=".jpg"))
        cv2.imwrite(str(tmp), patch)

        try:
            result = analyze_patch(
                image_path=tmp,
                qdrant=qdrant,
                models=models,
                config=config,
            )
        except Exception as e:
            result = {"errors": [str(e)]}
        finally:
            tmp.unlink()

        reid_info = result.get("reid", {})
        trace_id = reid_info.get("global_person_id", None)
        trace_id_short = trace_id[:8] if trace_id else "?"
        is_new = reid_info.get("is_new_person", None)
        quality = reid_info.get("quality_score", None)
        match_score = reid_info.get("match_score", None)

        par_info = result.get("par", {})
        par_attrs = par_info.get("attributes", {}) if par_info else {}
        top_par = sorted(par_attrs.items(), key=lambda x: x[1], reverse=True)[:5]
        top_par = [(k, v) for k, v in top_par if v > 0.5]

        errors = result.get("errors", [])

        record = {
            "frame": frame_idx,
            "tracking_id": track_id,
            "trace_id": trace_id,
            "is_new_person": is_new,
            "quality_score": quality,
            "match_score": match_score,
            "bbox": [x1, y1, x2, y2],
            "par": dict(top_par),
            "errors": errors,
        }
        frame_results.append(record)
        all_results.append(record)

        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 3)

        label_parts = [
            f"ID:{track_id}",
            f"trace:{trace_id_short}",
        ]
        if quality is not None:
            label_parts.append(f"qual:{quality:.2f}")
        if is_new is True:
            label_parts.append("NEW")
        elif is_new is False:
            label_parts.append("MATCH")
        elif is_new is None:
            label_parts.append("?")

        label = " ".join(label_parts)
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.8, 2)
        cv2.rectangle(frame, (x1, y1 - th - 10), (x1 + tw + 10, y1), color, -1)
        cv2.putText(frame, label, (x1 + 5, y1 - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)

        if top_par:
            par_label = " ".join([f"{k}:{v:.2f}" for k, v in top_par[:3]])
            par_y = y2 + 25
            (pw, ph), _ = cv2.getTextSize(par_label, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2)
            cv2.rectangle(frame, (x1, par_y - ph - 5), (x1 + pw + 10, par_y + 5), (0, 0, 0), -1)
            cv2.putText(frame, par_label, (x1 + 5, par_y), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

        total_processed += 1

    info = f"Frame: {frame_idx}/{total_frames}  Persons: {len(frame_results)}  Total: {total_processed}"
    cv2.putText(frame, info, (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 0), 2)

    out.write(frame)
    frame_idx += 1

    if frame_idx % 50 == 0:
        elapsed = time.time() - t_start
        fps_proc = frame_idx / elapsed if elapsed > 0 else 0
        print(f"  frame {frame_idx}/{total_frames}  ({fps_proc:.1f} frame_fps)  persons_detected={total_processed}")

cap.release()
out.release()

with open(RESULTS_JSON_PATH, "w") as f:
    json.dump(all_results, f, indent=2, ensure_ascii=False)

elapsed = time.time() - t_start
print("-" * 70)
print(f"Done! Processed {frame_idx} frames, {total_processed} person detections")
print(f"Output video: {OUTPUT_VIDEO_PATH}")
print(f"Results JSON: {RESULTS_JSON_PATH}")
print(f"Elapsed: {elapsed:.1f}s ({frame_idx/elapsed:.1f} frame_fps)")