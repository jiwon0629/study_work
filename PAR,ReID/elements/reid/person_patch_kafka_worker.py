import argparse
import base64
import json
import logging
import math
import os
import signal
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from confluent_kafka import Consumer, KafkaError

from .analyze_person_patch import (
    OnnxModels,
    analyze_patch,
    build_qdrant_adapter,
)
from .worker.publisher import MQTTPublisher


def _build_result_payload(
    event: Mapping[str, Any],
    analysis: Mapping[str, Any],
    include_patch: bool,
    patch_max_bytes: int,
    zone_status: str,
) -> dict[str, Any]:
    if not isinstance(event.get("object"), Mapping):
        raise ValueError("event.object must be a mapping")
    obj = event["object"]
    if not isinstance(event.get("patch"), Mapping):
        raise ValueError("event.patch must be a mapping")
    patch = event["patch"]

    reid = analysis.get("reid")
    if not isinstance(reid, Mapping):
        raise ValueError("analysis.reid must be a mapping")
    par = analysis.get("par")
    if par is None:
        par_payload = None
    elif isinstance(par, Mapping):
        par_attributes = par.get("attributes")
        if not isinstance(par_attributes, Mapping):
            raise ValueError("analysis.par.attributes must be a mapping")
        par_payload = par
    else:
        raise ValueError("analysis.par must be a mapping or null")

    patch_payload = None
    if include_patch:
        patch_b64 = patch.get("bytes_b64")
        if not isinstance(patch_b64, str) or not patch_b64:
            raise ValueError("event.patch.bytes_b64 must be a non-empty string")
        if patch_max_bytes > 0 and len(patch_b64.encode("utf-8")) > patch_max_bytes:
            raise ValueError(f"event.patch.bytes_b64 exceeds mqtt_patch_max_bytes={patch_max_bytes}")
        patch_payload = {
            "format": patch.get("format"),
            "width": patch.get("width"),
            "height": patch.get("height"),
            "image_b64": patch_b64,
        }

    timestamp_ns = event.get("timestamp_ns")
    if not isinstance(timestamp_ns, int):
        raise ValueError("event.timestamp_ns must be an integer")
    event_time_iso = datetime.fromtimestamp(timestamp_ns / 1_000_000_000, tz=timezone.utc).isoformat(
        timespec="milliseconds"
    )

    reid_payload = {
        "embedding_dim": reid.get("embedding_dim"),
        "match_score": reid.get("match_score"),
        "global_person_id": reid.get("global_person_id"),
        "is_new_person": reid.get("is_new_person"),
        "decision_reason": reid.get("decision_reason"),
    }
    if zone_status not in {"clear", "approach", "intrusion"}:
        raise ValueError(f"zone_status must be clear|approach|intrusion, got {zone_status}")

    return {
        "version": "v1",
        "event_id": event.get("event_id"),
        "stream_id": event.get("stream_id"),
        "frame_id": event.get("frame_id"),
        "event_time_iso": event_time_iso,
        "tracking_id": obj.get("tracking_id"),
        "reid": reid_payload,
        "par": par_payload,
        "person_similarity_score": reid.get("match_score"),
        "zone_event": {"status": zone_status},
        "patch": patch_payload,
    }


def _decode_patch(event: Mapping[str, Any]) -> bytes:
    patch = event.get("patch")
    if not isinstance(patch, Mapping):
        raise ValueError("patch is missing")
    b64 = patch.get("bytes_b64")
    if not isinstance(b64, str) or not b64:
        raise ValueError("patch.bytes_b64 is missing")
    return base64.b64decode(b64)


def _is_pose_gate_failed(analysis: Mapping[str, Any]) -> bool:
    pose = analysis.get("pose")
    if not isinstance(pose, Mapping):
        return False
    return pose.get("pose_ok") is False


def _event_fields(event: Mapping[str, Any]) -> tuple[str, str, str]:
    obj = event.get("object")
    if not isinstance(obj, Mapping):
        raise ValueError("event.object must be a mapping")
    stream_id = event.get("stream_id")
    tracking_id = obj.get("tracking_id")
    event_id = event.get("event_id")
    if stream_id in (None, ""):
        raise ValueError("event.stream_id is required")
    if tracking_id in (None, ""):
        raise ValueError("event.object.tracking_id is required")
    if event_id in (None, ""):
        raise ValueError("event.event_id is required")
    return (str(stream_id), str(tracking_id), str(event_id))


def _payload_fields(payload: Mapping[str, Any]) -> tuple[str, str, str]:
    stream_id = payload.get("stream_id")
    tracking_id = payload.get("tracking_id")
    event_id = payload.get("event_id")
    if stream_id in (None, ""):
        raise ValueError("payload.stream_id is required")
    if tracking_id in (None, ""):
        raise ValueError("payload.tracking_id is required")
    if event_id in (None, ""):
        raise ValueError("payload.event_id is required")
    return (str(stream_id), str(tracking_id), str(event_id))


def _reid_outcome(payload: Mapping[str, Any]) -> tuple[str, str]:
    reid = payload.get("reid")
    if not isinstance(reid, Mapping):
        raise ValueError("payload.reid must be a mapping")
    global_person_id = reid.get("global_person_id")
    is_new_person = reid.get("is_new_person")
    if global_person_id not in (None, ""):
        pid = str(global_person_id)
        if is_new_person is True:
            return "assigned_new_id", pid
        if is_new_person is False:
            return "mapped_existing_id", pid
        return "mapped_global_id", pid
    decision_reason = reid.get("decision_reason")
    if not isinstance(decision_reason, str) or not decision_reason:
        raise ValueError("payload.reid.decision_reason is required when global_person_id is missing")
    tracking_id = payload.get("tracking_id")
    if tracking_id in (None, ""):
        raise ValueError("payload.tracking_id is required when global_person_id is missing")
    return decision_reason, f"track:{tracking_id}"


def _pose_gate_metrics(analysis: Mapping[str, Any]) -> tuple[str, str, str, str]:
    pose = analysis.get("pose")
    if not isinstance(pose, Mapping):
        raise ValueError("analysis.pose must be a mapping")
    if "missing_regions" not in pose:
        raise ValueError("analysis.pose.missing_regions is required")
    if "threshold_default" not in pose:
        raise ValueError("analysis.pose.threshold_default is required")
    if "threshold_hip" not in pose:
        raise ValueError("analysis.pose.threshold_hip is required")
    if "threshold_distal" not in pose:
        raise ValueError("analysis.pose.threshold_distal is required")
    missing_regions = pose["missing_regions"]
    if not isinstance(missing_regions, list):
        raise ValueError("analysis.pose.missing_regions must be a list")
    return (
        ";".join(str(v) for v in missing_regions),
        str(pose["threshold_default"]),
        str(pose["threshold_hip"]),
        str(pose["threshold_distal"]),
    )


def _to_float(value: Any, field: str) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    raise ValueError(f"{field} must be numeric")


def _extract_bbox(event: Mapping[str, Any]) -> tuple[float, float, float, float]:
    obj = event.get("object")
    if not isinstance(obj, Mapping):
        raise ValueError("event.object must be a mapping")
    bbox = obj.get("bbox")
    if not isinstance(bbox, Mapping):
        raise ValueError("event.object.bbox must be a mapping")
    left = _to_float(bbox.get("left"), "event.object.bbox.left")
    top = _to_float(bbox.get("top"), "event.object.bbox.top")
    width = _to_float(bbox.get("width"), "event.object.bbox.width")
    height = _to_float(bbox.get("height"), "event.object.bbox.height")
    if width <= 0 or height <= 0:
        raise ValueError("event.object.bbox.width and height must be > 0")
    return (left, top, left + width, top + height)


def _extract_frame_size(event: Mapping[str, Any]) -> tuple[float, float]:
    frame_size = event.get("frame_size")
    if not isinstance(frame_size, Mapping):
        raise ValueError("event.frame_size must be a mapping")
    width = _to_float(frame_size.get("width"), "event.frame_size.width")
    height = _to_float(frame_size.get("height"), "event.frame_size.height")
    if width <= 0 or height <= 0:
        raise ValueError("event.frame_size.width and height must be > 0")
    return width, height


def _extract_watch_zone_points(event: Mapping[str, Any]) -> list[tuple[float, float]]:
    if "watch_zone_points" not in event:
        raise ValueError("event.watch_zone_points is required")
    raw_points = event.get("watch_zone_points")
    if not isinstance(raw_points, list):
        raise ValueError("event.watch_zone_points must be an array")
    if len(raw_points) == 0:
        return []
    if len(raw_points) < 3:
        raise ValueError("event.watch_zone_points must contain either 0 or at least 3 points")

    points: list[tuple[float, float]] = []
    for idx, raw_point in enumerate(raw_points):
        if not isinstance(raw_point, list) or len(raw_point) != 2:
            raise ValueError(f"event.watch_zone_points[{idx}] must contain exactly 2 numbers")
        x = _to_float(raw_point[0], f"event.watch_zone_points[{idx}][0]")
        y = _to_float(raw_point[1], f"event.watch_zone_points[{idx}][1]")
        points.append((x, y))
    return points


def _scale_watch_zone_points(
    points_1080p: list[tuple[float, float]],
    frame_width: float,
    frame_height: float,
) -> list[tuple[float, float]]:
    scale_x = frame_width / 1920.0
    scale_y = frame_height / 1080.0
    return [(x * scale_x, y * scale_y) for x, y in points_1080p]


def _point_in_rect(point: tuple[float, float], rect: tuple[float, float, float, float]) -> bool:
    x, y = point
    left, top, right, bottom = rect
    return left <= x <= right and top <= y <= bottom


def _point_in_polygon(point: tuple[float, float], polygon: list[tuple[float, float]]) -> bool:
    x, y = point
    inside = False
    n = len(polygon)
    for i in range(n):
        x1, y1 = polygon[i]
        x2, y2 = polygon[(i + 1) % n]
        intersects = ((y1 > y) != (y2 > y)) and (x < (x2 - x1) * (y - y1) / ((y2 - y1) or 1e-12) + x1)
        if intersects:
            inside = not inside
    return inside


def _orientation(a: tuple[float, float], b: tuple[float, float], c: tuple[float, float]) -> float:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _on_segment(a: tuple[float, float], b: tuple[float, float], p: tuple[float, float], eps: float = 1e-9) -> bool:
    return (
        min(a[0], b[0]) - eps <= p[0] <= max(a[0], b[0]) + eps
        and min(a[1], b[1]) - eps <= p[1] <= max(a[1], b[1]) + eps
    )


def _segments_intersect(
    a1: tuple[float, float],
    a2: tuple[float, float],
    b1: tuple[float, float],
    b2: tuple[float, float],
) -> bool:
    eps = 1e-9
    o1 = _orientation(a1, a2, b1)
    o2 = _orientation(a1, a2, b2)
    o3 = _orientation(b1, b2, a1)
    o4 = _orientation(b1, b2, a2)

    if ((o1 > eps and o2 < -eps) or (o1 < -eps and o2 > eps)) and (
        (o3 > eps and o4 < -eps) or (o3 < -eps and o4 > eps)
    ):
        return True

    if abs(o1) <= eps and _on_segment(a1, a2, b1):
        return True
    if abs(o2) <= eps and _on_segment(a1, a2, b2):
        return True
    if abs(o3) <= eps and _on_segment(b1, b2, a1):
        return True
    if abs(o4) <= eps and _on_segment(b1, b2, a2):
        return True
    return False


def _point_segment_distance(point: tuple[float, float], a: tuple[float, float], b: tuple[float, float]) -> float:
    px, py = point
    ax, ay = a
    bx, by = b
    dx = bx - ax
    dy = by - ay
    seg_len_sq = dx * dx + dy * dy
    if seg_len_sq <= 1e-12:
        return math.hypot(px - ax, py - ay)
    t = ((px - ax) * dx + (py - ay) * dy) / seg_len_sq
    t = max(0.0, min(1.0, t))
    cx = ax + t * dx
    cy = ay + t * dy
    return math.hypot(px - cx, py - cy)


def _segment_distance(
    a1: tuple[float, float],
    a2: tuple[float, float],
    b1: tuple[float, float],
    b2: tuple[float, float],
) -> float:
    if _segments_intersect(a1, a2, b1, b2):
        return 0.0
    return min(
        _point_segment_distance(a1, b1, b2),
        _point_segment_distance(a2, b1, b2),
        _point_segment_distance(b1, a1, a2),
        _point_segment_distance(b2, a1, a2),
    )


def _rect_corners(rect: tuple[float, float, float, float]) -> list[tuple[float, float]]:
    left, top, right, bottom = rect
    return [(left, top), (right, top), (right, bottom), (left, bottom)]


def _rect_edges(rect: tuple[float, float, float, float]) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    corners = _rect_corners(rect)
    return [(corners[i], corners[(i + 1) % 4]) for i in range(4)]


def _polygon_edges(
    polygon: list[tuple[float, float]],
) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    return [(polygon[i], polygon[(i + 1) % len(polygon)]) for i in range(len(polygon))]


def _polygon_bbox_overlap(rect: tuple[float, float, float, float], polygon: list[tuple[float, float]]) -> bool:
    rect_corners = _rect_corners(rect)
    if any(_point_in_polygon(point, polygon) for point in rect_corners):
        return True
    if any(_point_in_rect(point, rect) for point in polygon):
        return True

    for rect_edge in _rect_edges(rect):
        for poly_edge in _polygon_edges(polygon):
            if _segments_intersect(rect_edge[0], rect_edge[1], poly_edge[0], poly_edge[1]):
                return True
    return False


def _rect_polygon_min_distance(rect: tuple[float, float, float, float], polygon: list[tuple[float, float]]) -> float:
    if _polygon_bbox_overlap(rect, polygon):
        return 0.0

    min_distance = math.inf
    for rect_edge in _rect_edges(rect):
        for poly_edge in _polygon_edges(polygon):
            distance = _segment_distance(rect_edge[0], rect_edge[1], poly_edge[0], poly_edge[1])
            min_distance = min(min_distance, distance)
    return float(min_distance)


def _resolve_zone_status(event: Mapping[str, Any], zone_near_threshold_ratio: float) -> str:
    if zone_near_threshold_ratio <= 0 or zone_near_threshold_ratio > 1:
        raise ValueError("zone_near_threshold_ratio must be in (0, 1]")

    points_1080p = _extract_watch_zone_points(event)
    if len(points_1080p) == 0:
        return "clear"

    frame_width, frame_height = _extract_frame_size(event)
    watch_zone = _scale_watch_zone_points(points_1080p, frame_width, frame_height)
    bbox = _extract_bbox(event)

    if _polygon_bbox_overlap(bbox, watch_zone):
        return "intrusion"

    distance = _rect_polygon_min_distance(bbox, watch_zone)
    threshold = math.hypot(frame_width, frame_height) * zone_near_threshold_ratio
    if distance <= threshold:
        return "approach"
    return "clear"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Kafka worker for person patch analysis and MQTT publishing")
    parser.add_argument("--kafka-bootstrap-servers", required=True, help="Kafka bootstrap servers")
    parser.add_argument("--kafka-topic", required=True, help="Kafka topic")
    parser.add_argument("--kafka-group-id", required=True, help="Kafka consumer group id")
    parser.add_argument("--auto-offset-reset", required=True, choices=["latest", "earliest"], help="Offset reset")
    parser.add_argument("--max-poll-interval-ms", type=int, required=True, help="Max poll interval")
    parser.add_argument("--session-timeout-ms", type=int, required=True, help="Session timeout")
    parser.add_argument("--fetch-max-bytes", type=int, required=True, help="Max fetch bytes")
    parser.add_argument("--max-partition-fetch-bytes", type=int, required=True, help="Max partition fetch bytes")

    parser.add_argument("--mqtt-enabled", action=argparse.BooleanOptionalAction, required=True, help="Enable MQTT")
    parser.add_argument("--mqtt-broker-url", required=True, help="MQTT broker URL")
    parser.add_argument("--mqtt-topic-prefix", required=True, help="MQTT topic prefix")
    parser.add_argument("--mqtt-qos", type=int, required=True, help="MQTT QoS")
    parser.add_argument("--mqtt-queue-size", type=int, required=True, help="MQTT queue size")
    parser.add_argument("--mqtt-publish-timeout-ms", type=int, required=True, help="MQTT publish timeout")
    parser.add_argument("--mqtt-keepalive", type=int, required=True, help="MQTT keepalive")
    parser.add_argument("--mqtt-client-id", required=True, help="MQTT client id")
    parser.add_argument("--mqtt-username", required=True, help="MQTT username")
    parser.add_argument("--mqtt-password", required=True, help="MQTT password")
    parser.add_argument("--mqtt-max-retries", type=int, required=True, help="MQTT publish retries")
    parser.add_argument(
        "--mqtt-include-patch",
        action=argparse.BooleanOptionalAction,
        required=True,
        help="Include patch image_b64 in MQTT payload",
    )
    parser.add_argument(
        "--mqtt-patch-max-bytes",
        type=int,
        required=True,
        help="Max size for patch image_b64 bytes in MQTT payload",
    )

    parser.add_argument("--qdrant-url", required=True, help="Qdrant base URL")
    parser.add_argument("--collection", required=True, help="Qdrant collection")
    parser.add_argument("--person-profile-collection", required=True, help="Qdrant person profile collection")
    parser.add_argument("--t-match", type=float, required=True, help="Match threshold")
    parser.add_argument("--t-new", type=float, help="New-person threshold")
    parser.add_argument(
        "--score-direction",
        choices=["higher", "lower"],
        required=True,
        help="Score direction for Qdrant",
    )
    parser.add_argument(
        "--zone-near-threshold-ratio",
        type=float,
        required=True,
        help="Near-zone threshold ratio against frame diagonal",
    )
    parser.add_argument("--embed-dim", type=int, required=True, help="Embedding dimension")
    parser.add_argument("--save-embedding", action="store_true", help="Include embeddings in the output JSON")
    parser.add_argument("--pose-thresh-default", type=float, required=True, help="Default pose threshold")
    parser.add_argument("--pose-thresh-hip", type=float, required=True, help="Hip pose threshold")
    parser.add_argument("--pose-thresh-distal", type=float, required=True, help="Distal pose threshold")
    parser.add_argument("--movenet-onnx", required=True, help="MoveNet ONNX path")
    parser.add_argument("--reid-onnx", required=True, help="PASS-ReID ONNX path")
    parser.add_argument("--promptpar-onnx", required=True, help="PromptPAR ONNX path")
    parser.add_argument(
        "--promptpar-attributes",
        required=True,
        help="PromptPAR attribute labels path",
    )
    parser.add_argument("--prototype-max-per-person", type=int, required=True, help="Max prototypes per person id")
    parser.add_argument("--prototype-search-k", type=int, required=True, help="Top-K prototype search size")
    parser.add_argument(
        "--prototype-person-score-top-n",
        type=int,
        required=True,
        help="Top-N prototype average used for person score",
    )
    parser.add_argument(
        "--prototype-min-quality", type=float, required=True, help="Minimum quality for prototype insert"
    )
    parser.add_argument("--prototype-min-margin", type=float, required=True, help="Minimum margin for prototype insert")
    parser.add_argument(
        "--prototype-min-interval-sec",
        type=float,
        required=True,
        help="Minimum interval between prototype inserts for same person",
    )
    parser.add_argument(
        "--prototype-similarity-redundancy-threshold",
        type=float,
        required=True,
        help="Skip insert if prototype similarity is above threshold",
    )
    parser.add_argument(
        "--prototype-eviction-policy",
        required=True,
        choices=["lowest_quality_then_oldest"],
        help="Prototype eviction policy",
    )
    parser.add_argument("--quality-pose-weight", type=float, required=True, help="Pose component weight")
    parser.add_argument("--quality-sharpness-weight", type=float, required=True, help="Sharpness component weight")
    parser.add_argument("--quality-margin-weight", type=float, required=True, help="Margin component weight")
    parser.add_argument("--quality-sharpness-ref", type=float, required=True, help="Sharpness normalization reference")
    parser.add_argument("--worker-no", type=int, required=True, help="Worker index for logging")
    return parser.parse_args()


def _commit_offset(consumer: Consumer, msg) -> None:
    consumer.commit(message=msg, asynchronous=False)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    args = parse_args()
    if args.mqtt_enabled and not args.mqtt_broker_url:
        logging.error("mqtt-enabled requires --mqtt-broker-url")
        return 1

    config = {
        "t_match": args.t_match,
        "t_new": args.t_new,
        "save_embedding": args.save_embedding,
        "score_direction": args.score_direction,
        "zone_near_threshold_ratio": args.zone_near_threshold_ratio,
        "pose_threshold_default": args.pose_thresh_default,
        "pose_threshold_hip": args.pose_thresh_hip,
        "pose_threshold_distal": args.pose_thresh_distal,
        "prototype_max_per_person": args.prototype_max_per_person,
        "prototype_search_k": args.prototype_search_k,
        "prototype_person_score_top_n": args.prototype_person_score_top_n,
        "prototype_min_quality": args.prototype_min_quality,
        "prototype_min_margin": args.prototype_min_margin,
        "prototype_min_interval_sec": args.prototype_min_interval_sec,
        "prototype_similarity_redundancy_threshold": args.prototype_similarity_redundancy_threshold,
        "prototype_eviction_policy": args.prototype_eviction_policy,
        "quality_pose_weight": args.quality_pose_weight,
        "quality_sharpness_weight": args.quality_sharpness_weight,
        "quality_margin_weight": args.quality_margin_weight,
        "quality_sharpness_ref": args.quality_sharpness_ref,
        "person_profile_collection": args.person_profile_collection,
    }

    try:
        models = OnnxModels(
            movenet_path=Path(args.movenet_onnx),
            reid_path=Path(args.reid_onnx),
            promptpar_path=Path(args.promptpar_onnx),
            promptpar_attributes=Path(args.promptpar_attributes),
            pose_threshold_default=float(args.pose_thresh_default),
            pose_threshold_hip=float(args.pose_thresh_hip),
            pose_threshold_distal=float(args.pose_thresh_distal),
        )
        if args.embed_dim != models.embed_dim:
            logging.error("embed-dim %s does not match model output %s", args.embed_dim, models.embed_dim)
            return 1
        config["embed_dim"] = models.embed_dim
    except Exception as exc:
        logging.error("Failed to initialize models: %s", exc)
        return 1

    try:
        qdrant = build_qdrant_adapter(args.qdrant_url, args.collection, args.person_profile_collection)
    except Exception as exc:
        logging.error("Failed to initialize Qdrant: %s", exc)
        return 1

    publisher = None
    if args.mqtt_enabled:
        try:
            publisher = MQTTPublisher(
                broker_url=args.mqtt_broker_url,
                qos=args.mqtt_qos,
                client_id=args.mqtt_client_id,
                username=args.mqtt_username,
                password=args.mqtt_password,
                queue_size=args.mqtt_queue_size,
                publish_timeout_ms=args.mqtt_publish_timeout_ms,
                keepalive=args.mqtt_keepalive,
                max_retries=args.mqtt_max_retries,
            )
        except Exception as exc:
            logging.error("Failed to initialize MQTT publisher: %s", exc)
            return 1

    consumer = Consumer(
        {
            "bootstrap.servers": args.kafka_bootstrap_servers,
            "group.id": args.kafka_group_id,
            "enable.auto.commit": False,
            "auto.offset.reset": args.auto_offset_reset,
            "max.poll.interval.ms": args.max_poll_interval_ms,
            "session.timeout.ms": args.session_timeout_ms,
            "fetch.max.bytes": args.fetch_max_bytes,
            "max.partition.fetch.bytes": args.max_partition_fetch_bytes,
        }
    )
    consumer.subscribe([args.kafka_topic])

    stop_event = threading.Event()

    def handle_signal(signum, frame):
        logging.info("Signal %s received, shutting down", signum)
        stop_event.set()
        if publisher:
            publisher.stop_event.set()

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    if not isinstance(config.get("embed_dim"), int):
        raise ValueError("embed_dim must be resolved before entering the worker loop")

    try:
        while not stop_event.is_set():
            msg = consumer.poll(1.0)
            if msg is None:
                continue
            if msg.error():
                if msg.error().code() == KafkaError._PARTITION_EOF:
                    continue
                raise RuntimeError(f"Kafka consume error: {msg.error()}")

            raw = msg.value()
            if raw is None:
                raise ValueError("Kafka message value is empty")

            try:
                event = json.loads(raw.decode("utf-8"))
            except Exception as exc:
                raise ValueError(f"invalid JSON payload: {exc}") from exc

            stream_id, tracking_id, event_id = _event_fields(event)
            zone_status = _resolve_zone_status(
                event=event,
                zone_near_threshold_ratio=args.zone_near_threshold_ratio,
            )
            logging.info(
                "person_patch_event worker_no=%s worker_triggered=true stream_id=%s tracking_id=%s event_id=%s status=received",
                args.worker_no,
                stream_id,
                tracking_id,
                event_id,
            )

            try:
                patch_bytes = _decode_patch(event)
            except Exception as exc:
                raise ValueError(f"patch decode failed: {exc}") from exc

            temp_path = None
            try:
                with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tmp:
                    tmp.write(patch_bytes)
                    temp_path = tmp.name
                analysis: Mapping[str, Any] = analyze_patch(
                    image_path=temp_path, qdrant=qdrant, models=models, config=config
                )
            except Exception as exc:
                raise RuntimeError(f"patch analysis failed: {exc}") from exc
            finally:
                if temp_path:
                    try:
                        os.unlink(temp_path)
                    except OSError as exc:
                        raise RuntimeError(f"failed to clean up temp patch: {exc}") from exc

            pose_gate_failed = _is_pose_gate_failed(analysis)
            if pose_gate_failed:
                missing_regions, threshold_default, threshold_hip, threshold_distal = _pose_gate_metrics(analysis)
                logging.info(
                    "person_patch_event worker_no=%s worker_triggered=true stream_id=%s tracking_id=%s event_id=%s status=pose_gate_failed missing_regions=%s threshold_default=%s threshold_hip=%s threshold_distal=%s",
                    args.worker_no,
                    stream_id,
                    tracking_id,
                    event_id,
                    missing_regions,
                    threshold_default,
                    threshold_hip,
                    threshold_distal,
                )

            payload = _build_result_payload(
                event=event,
                analysis=analysis,
                include_patch=args.mqtt_include_patch,
                patch_max_bytes=args.mqtt_patch_max_bytes,
                zone_status=zone_status,
            )
            payload_json = json.dumps(payload, ensure_ascii=True)
            payload_stream_id, payload_tracking_id, payload_event_id = _payload_fields(payload)

            accepted = True
            if publisher:
                topic = f"{args.mqtt_topic_prefix.rstrip('/')}/{payload_stream_id}"
                accepted = publisher.enqueue(topic, payload_json)
                if not accepted:
                    raise RuntimeError("MQTT publish queue full")
            else:
                print(payload_json, flush=True)

            outcome, person_id = _reid_outcome(payload)
            logging.info(
                "person_patch_event worker_no=%s worker_triggered=true stream_id=%s tracking_id=%s event_id=%s status=published outcome=%s person_id=%s",
                args.worker_no,
                payload_stream_id,
                payload_tracking_id,
                payload_event_id,
                outcome,
                person_id,
            )
            _commit_offset(consumer, msg)

    except Exception:
        logging.exception("Worker failed")
        return 1

    finally:
        consumer.close()
        if publisher:
            publisher.close()
        logging.info("Worker stopped")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
