"""
멀티 카메라 실시간 추론 서버 — WebRTC 대시보드용 (멀티 GPU 지원)

- RTSP 수신 (끊김 시 자동 재연결)
- YOLO26 탐지 + IoU 트래킹 -> 트랙별 패치 crop -> PAR/MoveNet/ReID 분석
  (RT-DETR 엔진 GPU 아키텍처 문제 해결 전까지 YOLO26로 임시 대체)
- 영상: aiortc로 WebRTC 트랙 송출 (카메라별 1트랙)
- 분석 결과: WebSocket으로 프레임마다 JSON 송출

멀티 GPU 사용법 (GPU 2개, 카메라 3대를 GPU0/GPU1로 분리):
    # 터미널 1 - cam1, cam2를 GPU 0에서 처리, 포트 8080
    CUDA_VISIBLE_DEVICES=0 python3 inference_server.py --port 8080 --cameras cam1,cam2

    # 터미널 2 - cam3를 GPU 1에서 처리, 포트 8081
    CUDA_VISIBLE_DEVICES=1 python3 inference_server.py --port 8081 --cameras cam3

각 프로세스는 CUDA_VISIBLE_DEVICES로 지정된 GPU만 보게 되므로, 프로세스 내부에서는
그냥 기본 GPU(cuda:0)를 쓰면 실제로는 지정한 물리 GPU에서 돈다.
대시보드(static/dashboard.html)는 카메라별로 어느 포트에 붙을지 CAMERA_SERVERS에서 설정한다.
"""
import argparse
import asyncio
import os
import sys
import tempfile
import threading
import time
from pathlib import Path

os.environ.setdefault("CUDA_VISIBLE_DEVICES", "0")  # 외부에서 이미 지정했으면 그 값을 그대로 사용

parser = argparse.ArgumentParser()
parser.add_argument("--port", type=int, default=8080)
parser.add_argument(
    "--cameras", type=str, default="",
    help="이 프로세스가 처리할 카메라 id, 콤마로 구분 (예: cam1,cam2). 비우면 전체."
)
args, _ = parser.parse_known_args()

import cv2
import numpy as np
import av
from aiortc import RTCPeerConnection, RTCSessionDescription, VideoStreamTrack
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import uvicorn

# 실제 프로젝트 루트 경로 - 워크스테이션 구조에 맞춤
ELEMENTS_BASE = "/home/dev/workspace/model_test(PAR_ReID_OD)"
sys.path.insert(0, f"{ELEMENTS_BASE}/elements")  # reid 패키지가 여기 바로 밑에 있음

from ultralytics import YOLO
from qdrant_client import QdrantClient
from qdrant_client.http import models as rest
from reid.analyzer.service import OnnxModels, QdrantAdapter, analyze_patch

# ─── 설정 ──────────────────────────────────────────────────────
# 실제 카메라 RTSP 주소로 교체하세요. (전체 카메라 목록 - 실행 시 --cameras로 일부만 선택 가능)
ALL_CAMERAS = {
    "cam1": "rtsp://admin:qazwsx123!@192.168.0.22:554/0/H.264/media.smp", # 한화비전 - 25
    "cam2": "rtsp://admin:qazwsx123!@192.168.0.16:554/H.264/media.smp",# 한화비전
    "cam3": "rtsp://admin:qazwsx123!@192.168.0.77:554/H.264/media.smp",# 한화비전
    "cam4": "rtsp://admin:qazwsx123!@192.168.0.11:554/0/H.264/media.smp", # 한화비전
    "cam5": "rtsp://admin:qazwsx123!@192.168.0.14:554/4/H.264/media.smp", # 한화비전 - 17
}

YOLO_CONF_THRESH = 0.5
IOU_TRACK_MATCH_THRESH = 0.3
MAX_LOST_FRAMES = 15

PAR_CONFIG = {
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

RECONNECT_DELAY = 2.0
STALE_FRAME_SEC = 2.0
WS_PUSH_INTERVAL = 0.1
ANALYSIS_INTERVAL_FRAMES = 10  # 트랙별 PAR/ReID/MoveNet 재분석 주기 (매 프레임 X, N프레임마다)


# ─── IoU 트래커 ─────────────────────────────────────────────────
class Track:
    def __init__(self, track_id, bbox, frame_idx):
        self.track_id = track_id
        self.bbox = bbox
        self.last_frame = frame_idx
        self.lost_count = 0


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
            best_iou, best_idx = 0, -1
            for i, (dbox, _) in enumerate(detections):
                if matched[i]:
                    continue
                iou = self._iou(track.bbox, dbox)
                if iou > best_iou:
                    best_iou, best_idx = iou, i
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
        return [(t.track_id, t.bbox) for t in self.tracks if t.lost_count == 0]

    @staticmethod
    def _iou(a, b):
        x1, y1 = max(a[0], b[0]), max(a[1], b[1])
        x2, y2 = min(a[2], b[2]), min(a[3], b[3])
        inter = max(0, x2 - x1) * max(0, y2 - y1)
        area_a = (a[2] - a[0]) * (a[3] - a[1])
        area_b = (b[2] - b[0]) * (b[3] - b[1])
        union = area_a + area_b - inter
        return inter / union if union > 0 else 0


# ─── RTSP 안정 수신 (자동 재연결) ─────────────────────────────────
class RTSPStream:
    def __init__(self, url, reconnect_delay=RECONNECT_DELAY):
        self.url = url
        self.reconnect_delay = reconnect_delay
        self.frame = None
        self.lock = threading.Lock()
        self.running = True
        self.last_frame_time = 0.0
        self.cap = None
        self._open()
        self.thread = threading.Thread(target=self._reader, daemon=True)
        self.thread.start()

    def _open(self):
        if self.cap is not None:
            self.cap.release()
        os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp"
        self.cap = cv2.VideoCapture(self.url, cv2.CAP_FFMPEG)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    def _reader(self):
        while self.running:
            if self.cap is None or not self.cap.isOpened():
                time.sleep(self.reconnect_delay)
                self._open()
                continue
            ret, frame = self.cap.read()
            if not ret:
                time.sleep(self.reconnect_delay)
                self._open()
                continue
            with self.lock:
                self.frame = frame
                self.last_frame_time = time.time()

    def get_latest(self, max_age=STALE_FRAME_SEC):
        with self.lock:
            if self.frame is None or time.time() - self.last_frame_time > max_age:
                return None
            return self.frame.copy()

    def is_connected(self, max_age=STALE_FRAME_SEC):
        with self.lock:
            return self.frame is not None and time.time() - self.last_frame_time <= max_age

    def stop(self):
        self.running = False
        self.thread.join(timeout=2)
        if self.cap:
            self.cap.release()


# ─── 공용 모델 로딩 ────────────────────────────────────────────
print("모델 로딩 중...")
qdrant_client = QdrantClient(location=":memory:")
for name in ["person_embeddings", "person_profiles"]:
    qdrant_client.create_collection(
        collection_name=name,
        vectors_config=rest.VectorParams(size=768, distance=rest.Distance.COSINE),
    )

onnx_models = OnnxModels(
    movenet_path=Path(f"{ELEMENTS_BASE}/model_repository/movenet/model.onnx"),
    reid_path=Path(f"{ELEMENTS_BASE}/model_repository/reid/pass_transreid_vit_small.onnx"),
    promptpar_path=Path(f"{ELEMENTS_BASE}/model_repository/par/promptpar_pa100k.onnx"),
    promptpar_attributes=Path(f"{ELEMENTS_BASE}/model_repository/par/pa100k_attributes.txt"),
    pose_threshold_default=0.15,
    pose_threshold_hip=0.15,
    pose_threshold_distal=0.05,
)
PAR_CONFIG["embed_dim"] = onnx_models.embed_dim

# RT-DETR 엔진 문제(compute 8.9 vs 8.6) 해결 전까지 YOLO26으로 임시 대체
yolo_model = YOLO("yolo26n.pt", task="detect")
print("모델 로딩 완료")

_qdrant_adapters: dict[str, QdrantAdapter] = {}

# trace_id(ReID 전역 정체성) -> 화면에 보여줄 짧은 번호. 카메라 전체가 공유.
# tracking_id는 카메라별 IoU 연속성 추적용이라 원리적으로 카메라 간 통일이 안 되지만,
# 이 display_id는 trace_id 기준이라 ReID 매칭에 성공하면 카메라가 달라도 같은 번호로 보인다.
_display_id_lock = threading.Lock()
_display_ids: dict[str, int] = {}
_display_id_counter = [0]


def get_display_id(trace_id: str | None) -> int | None:
    if not trace_id:
        return None
    with _display_id_lock:
        if trace_id not in _display_ids:
            _display_id_counter[0] += 1
            _display_ids[trace_id] = _display_id_counter[0]
        return _display_ids[trace_id]


def qdrant_adapter_for(camera_id: str) -> QdrantAdapter:
    if camera_id not in _qdrant_adapters:
        _qdrant_adapters[camera_id] = QdrantAdapter(
            qdrant_client, "person_embeddings", "person_profiles", rest
        )
    return _qdrant_adapters[camera_id]


# ─── 카메라별 워커 ─────────────────────────────────────────────
class CameraWorker:
    def __init__(self, camera_id: str, rtsp_url: str):
        self.camera_id = camera_id
        self.stream = RTSPStream(rtsp_url)
        self.tracker = SimpleTracker(IOU_TRACK_MATCH_THRESH, MAX_LOST_FRAMES)
        self.state_lock = threading.Lock()
        self.latest_frame = None
        self.latest_results = []
        self.frame_idx = 0
        self.connected = False
        self.running = True
        self.track_cache: dict[int, dict] = {}  # track_id -> {"result": ..., "last_frame": ...}
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _run(self):
        while self.running:
            frame = self.stream.get_latest()
            self.connected = self.stream.is_connected()
            if frame is None:
                time.sleep(0.05)
                continue

            height, width = frame.shape[:2]
            results = yolo_model(frame, classes=[0], conf=YOLO_CONF_THRESH, verbose=False)
            detections = []
            for r in results:
                if r.boxes is None:
                    continue
                for box in r.boxes:
                    detections.append((box.xyxy[0].tolist(), float(box.conf)))

            self.tracker.update(detections, self.frame_idx)

            active_ids = set()
            frame_results = []
            for track_id, bbox in self.tracker.active_tracks():
                active_ids.add(track_id)
                x1, y1, x2, y2 = map(int, bbox)
                x1, y1 = max(0, x1), max(0, y1)
                x2, y2 = min(width - 1, x2), min(height - 1, y2)
                if x2 <= x1 or y2 <= y1:
                    continue

                cached = self.track_cache.get(track_id)
                need_analysis = (
                    cached is None
                    or (self.frame_idx - cached["last_frame"]) >= ANALYSIS_INTERVAL_FRAMES
                )

                if need_analysis:
                    patch = frame[y1:y2, x1:x2]
                    if patch.size == 0:
                        continue
                    result = self._analyze(track_id, patch, [x1, y1, x2, y2])
                    self.track_cache[track_id] = {"result": result, "last_frame": self.frame_idx}
                else:
                    # 캐시된 PAR/ReID 결과는 재사용하고, 위치(bbox)만 최신으로 갱신
                    result = dict(cached["result"])
                    result["bbox"] = [x1, y1, x2, y2]
                    result["frame"] = self.frame_idx

                frame_results.append(result)

            # 더 이상 안 보이는 트랙의 캐시는 정리 (메모리 누적 방지)
            stale_ids = set(self.track_cache) - active_ids
            for tid in stale_ids:
                del self.track_cache[tid]

            with self.state_lock:
                self.latest_frame = frame
                self.latest_results = frame_results
            self.frame_idx += 1

    def _analyze(self, track_id, patch, bbox):
        tmp = Path(tempfile.mktemp(suffix=".jpg"))
        cv2.imwrite(str(tmp), patch)
        try:
            result = analyze_patch(
                image_path=tmp,
                qdrant=qdrant_adapter_for(self.camera_id),
                models=onnx_models,
                config=PAR_CONFIG,
            )
        except Exception as e:
            result = {"errors": [str(e)]}
        finally:
            tmp.unlink(missing_ok=True)

        reid_info = result.get("reid", {}) or {}
        par_info = result.get("par", {}) or {}
        par_attrs = par_info.get("attributes", {}) if par_info else {}
        top_par = sorted(par_attrs.items(), key=lambda x: x[1], reverse=True)[:5]
        top_par = {k: round(v, 3) for k, v in top_par if v > 0.5}

        return {
            "camera_id": self.camera_id,
            "frame": self.frame_idx,
            "tracking_id": track_id,
            "display_id": get_display_id(reid_info.get("global_person_id")),
            "trace_id": reid_info.get("global_person_id"),
            "is_new_person": reid_info.get("is_new_person"),
            "quality_score": reid_info.get("quality_score"),
            "match_score": reid_info.get("match_score"),
            "match_margin": reid_info.get("match_margin"),
            "decision_reason": reid_info.get("decision_reason"),
            "pose_gate_failed": (result.get("pose") or {}).get("pose_ok") is False,
            "bbox": bbox,
            "par": top_par,
            "pose": result.get("pose"),
            "errors": result.get("errors", []),
        }

    def get_frame_and_results(self):
        with self.state_lock:
            frame = None if self.latest_frame is None else self.latest_frame.copy()
            return frame, list(self.latest_results)

    def stop(self):
        self.running = False
        self.thread.join(timeout=2)
        self.stream.stop()


CAMERAS = (
    {cid: url for cid, url in ALL_CAMERAS.items() if cid in args.cameras.split(",")}
    if args.cameras
    else ALL_CAMERAS
)
if not CAMERAS:
    raise SystemExit(f"--cameras에 매칭되는 카메라가 없습니다: {args.cameras}")
print(f"이 프로세스가 처리할 카메라: {list(CAMERAS.keys())} (GPU: {os.environ.get('CUDA_VISIBLE_DEVICES')})")

workers: dict[str, CameraWorker] = {
    cam_id: CameraWorker(cam_id, url) for cam_id, url in CAMERAS.items()
}


# ─── WebRTC 비디오 트랙 ────────────────────────────────────────
class CameraVideoTrack(VideoStreamTrack):
    def __init__(self, worker: CameraWorker):
        super().__init__()
        self.worker = worker

    async def recv(self):
        pts, time_base = await self.next_timestamp()
        frame, _ = self.worker.get_frame_and_results()
        if frame is None:
            frame = np.zeros((480, 640, 3), dtype=np.uint8)
            cv2.putText(frame, f"{self.worker.camera_id}: connecting...", (30, 240),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 255), 2)

        video_frame = av.VideoFrame.from_ndarray(frame, format="bgr24")
        video_frame.pts = pts
        video_frame.time_base = time_base
        return video_frame


# ─── FastAPI ───────────────────────────────────────────────────
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

pcs: set[RTCPeerConnection] = set()


class Offer(BaseModel):
    sdp: str
    type: str


@app.post("/offer/{camera_id}")
async def offer(camera_id: str, params: Offer):
    if camera_id not in workers:
        return {"error": f"unknown camera_id: {camera_id}"}

    pc = RTCPeerConnection()
    pcs.add(pc)

    @pc.on("connectionstatechange")
    async def on_state_change():
        if pc.connectionState in ("failed", "closed"):
            pcs.discard(pc)
            await pc.close()

    pc.addTrack(CameraVideoTrack(workers[camera_id]))

    await pc.setRemoteDescription(RTCSessionDescription(sdp=params.sdp, type=params.type))
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)

    return {"sdp": pc.localDescription.sdp, "type": pc.localDescription.type}


@app.websocket("/ws/{camera_id}")
async def ws_metadata(websocket: WebSocket, camera_id: str):
    await websocket.accept()
    if camera_id not in workers:
        await websocket.send_json({"error": f"unknown camera_id: {camera_id}"})
        await websocket.close()
        return

    worker = workers[camera_id]
    try:
        while True:
            _, results = worker.get_frame_and_results()
            await websocket.send_json({
                "camera_id": camera_id,
                "connected": worker.connected,
                "frame": worker.frame_idx,
                "tracks": results,
            })
            await asyncio.sleep(WS_PUSH_INTERVAL)
    except WebSocketDisconnect:
        pass


@app.get("/cameras")
async def list_cameras():
    return {
        cam_id: {"connected": w.connected, "frame": w.frame_idx}
        for cam_id, w in workers.items()
    }


@app.get("/debug/qdrant")
async def debug_qdrant():
    """
    person_profiles 컬렉션에 등록된 모든 사람(정체성)을 그대로 덤프.
    같은 물리적 인물이 trace_id 여러 개로 중복 등록되어 있는지,
    카메라별로 컬렉션/데이터가 실제로 공유되고 있는지 확인하는 용도.
    """
    points, _ = qdrant_client.scroll(
        collection_name="person_profiles",
        limit=200,
        with_payload=True,
        with_vectors=False,
    )
    embedding_points, _ = qdrant_client.scroll(
        collection_name="person_embeddings",
        limit=500,
        with_payload=True,
        with_vectors=False,
    )
    return {
        "person_profiles_count": len(points),
        "person_profiles": [{"id": str(p.id), "payload": p.payload} for p in points],
        "person_embeddings_count": len(embedding_points),
        "person_embeddings_sample": [
            {"id": str(p.id), "payload": p.payload} for p in embedding_points[:20]
        ],
    }


# 대시보드 정적 파일 서빙 (static/dashboard.html)
static_dir = Path(__file__).parent / "static"
static_dir.mkdir(exist_ok=True)
app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=args.port)