"""Minimal patch analyzer with Qdrant lookup and ONNX models."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping, Protocol, Sequence


class QdrantClientProtocol(Protocol):
    """Minimum Qdrant interface needed by the analyzer."""

    def search(self, *, embedding: list[float], top_k: int, with_payload: bool) -> list[dict[str, object]]:
        """Return a list of matches with id/score fields."""

    def upsert(self, *, id: str, embedding: list[float], payload: dict[str, object]) -> None:
        """Upsert a single embedding with payload."""

    def list_person_points(self, *, person_id: str) -> list[dict[str, object]]:
        """Return points for a person_id from payload index."""

    def delete_points(self, *, ids: list[str]) -> None:
        """Delete points by IDs."""

    def get_person_profile_par(self, *, person_id: str) -> dict[str, object] | None:
        """Return PAR attributes stored in the profile collection."""

    def upsert_person_profile_par(
        self,
        *,
        person_id: str,
        embedding: list[float],
        par_attributes: Mapping[str, object],
        now: datetime,
    ) -> None:
        """Insert or update 1:1 profile PAR for person_id."""


class QdrantAdapter:
    """Adapter that supports modern Qdrant search APIs."""

    def __init__(
        self,
        client: object,
        prototype_collection_name: str,
        profile_collection_name: str,
        rest_module: object,
    ) -> None:
        """Store client dependencies and select a search mode."""
        self._client = client
        self._prototype_collection = prototype_collection_name
        self._profile_collection = profile_collection_name
        self._rest = rest_module
        if hasattr(client, "query_points"):
            self._search_mode = "query_points"
        elif hasattr(client, "search"):
            self._search_mode = "search"
        else:
            raise AttributeError("Qdrant client lacks query/search endpoints")
        self._ensure_collection_exists(self._profile_collection)

    def _ensure_collection_exists(self, collection_name: str) -> None:
        if hasattr(self._client, "collection_exists"):
            exists = self._client.collection_exists(collection_name=collection_name)
            if exists:
                return
            raise RuntimeError(f"Qdrant collection does not exist: {collection_name}")
        try:
            self._client.get_collection(collection_name=collection_name)
        except Exception as exc:
            raise RuntimeError(f"Qdrant collection does not exist: {collection_name}") from exc

    def _search_query_points(self, embedding: list[float], top_k: int, with_payload: bool) -> list[object]:
        response = self._client.query_points(
            collection_name=self._prototype_collection,
            query=embedding,
            limit=top_k,
            with_payload=with_payload,
            with_vectors=False,
        )
        return getattr(response, "points", [])

    def search(self, *, embedding: list[float], top_k: int, with_payload: bool) -> list[dict[str, object]]:
        """Search the Qdrant collection and return scored matches."""
        if self._search_mode == "query_points":
            points = self._search_query_points(embedding, top_k, with_payload)
        else:
            points = self._client.search(
                collection_name=self._prototype_collection,
                query_vector=embedding,
                limit=top_k,
                with_payload=with_payload,
            )
        search_results: list[dict[str, object]] = []
        for point in points:
            payload = getattr(point, "payload", None)
            if not isinstance(payload, Mapping):
                payload = {}
            search_results.append(
                {
                    "id": str(point.id),
                    "score": float(point.score),
                    "payload": dict(payload),
                }
            )
        return search_results

    def upsert(self, *, id: str, embedding: list[float], payload: dict[str, object]) -> None:
        """Insert or update a single point."""
        self._client.upsert(
            collection_name=self._prototype_collection,
            points=[self._rest.PointStruct(id=id, vector=embedding, payload=payload)],
        )

    def list_person_points(self, *, person_id: str) -> list[dict[str, object]]:
        """Scroll points that belong to a person id."""
        condition = self._rest.FieldCondition(
            key="person_id",
            match=self._rest.MatchValue(value=person_id),
        )
        points: list[dict[str, object]] = []
        offset = None
        while True:
            kwargs = {
                "collection_name": self._prototype_collection,
                "limit": 128,
                "with_payload": True,
                "with_vectors": False,
                "offset": offset,
            }
            scroll_filter = self._rest.Filter(must=[condition])
            try:
                batch, offset = self._client.scroll(scroll_filter=scroll_filter, **kwargs)
            except TypeError:
                batch, offset = self._client.scroll(query_filter=scroll_filter, **kwargs)
            for point in batch:
                payload = getattr(point, "payload", None)
                if not isinstance(payload, Mapping):
                    payload = {}
                points.append({"id": str(point.id), "payload": dict(payload)})
            if offset is None:
                break
        return points

    def delete_points(self, *, ids: list[str]) -> None:
        """Delete points by IDs."""
        if not ids:
            return
        selector = self._rest.PointIdsList(points=ids)
        try:
            self._client.delete(
                collection_name=self._prototype_collection,
                points_selector=selector,
                wait=True,
            )
        except TypeError:
            self._client.delete(
                collection_name=self._prototype_collection,
                points_selector=selector,
            )

    def _retrieve_profile_points(self, person_id: str) -> list[object]:
        if hasattr(self._client, "retrieve"):
            points = self._client.retrieve(
                collection_name=self._profile_collection,
                ids=[person_id],
                with_payload=True,
                with_vectors=False,
            )
            if points:
                return points
        condition = self._rest.FieldCondition(
            key="person_id",
            match=self._rest.MatchValue(value=person_id),
        )
        scroll_filter = self._rest.Filter(must=[condition])
        kwargs = {
            "collection_name": self._profile_collection,
            "limit": 1,
            "with_payload": True,
            "with_vectors": False,
        }
        try:
            batch, _ = self._client.scroll(scroll_filter=scroll_filter, **kwargs)
        except TypeError:
            batch, _ = self._client.scroll(query_filter=scroll_filter, **kwargs)
        return list(batch)

    def _existing_profile_payload(self, person_id: str) -> Mapping[str, object] | None:
        points = self._retrieve_profile_points(person_id)
        if not points:
            return None
        payload = getattr(points[0], "payload", None)
        if isinstance(payload, Mapping):
            return payload
        return None

    def get_person_profile_par(self, *, person_id: str) -> dict[str, object] | None:
        payload = self._existing_profile_payload(person_id)
        if not isinstance(payload, Mapping):
            return None
        raw = payload.get("par_attributes")
        if not isinstance(raw, Mapping):
            return None
        return {str(key): value for key, value in raw.items()}

    def upsert_person_profile_par(
        self,
        *,
        person_id: str,
        embedding: list[float],
        par_attributes: Mapping[str, object],
        now: datetime,
    ) -> None:
        now_iso = now.isoformat(timespec="milliseconds")
        existing_payload = self._existing_profile_payload(person_id)
        created_at = now_iso
        if isinstance(existing_payload, Mapping):
            existing_created_at = existing_payload.get("created_at")
            if isinstance(existing_created_at, str) and existing_created_at:
                created_at = existing_created_at
        payload = {
            "person_id": person_id,
            "par_attributes": dict(par_attributes),
            "created_at": created_at,
            "updated_at": now_iso,
        }
        self._client.upsert(
            collection_name=self._profile_collection,
            points=[self._rest.PointStruct(id=person_id, vector=embedding, payload=payload)],
        )


class ModelsProtocol(Protocol):
    """Minimum model interface needed by the analyzer."""

    expects_image: bool

    def movenet(self, image: object) -> Mapping[str, object]:
        """Return pose details used for gating."""

    def pass_reid(self, image: object) -> Sequence[float]:
        """Return re-identification embedding."""

    def promptpar(self, image: object) -> Mapping[str, object]:
        """Return attribute predictions for new people."""


class OnnxModels:
    """ONNX Runtime model bundle for pose, re-id, and PromptPAR."""

    expects_image = True

    def __init__(
        self,
        *,
        movenet_path: Path,
        reid_path: Path,
        promptpar_path: Path,
        promptpar_attributes: Path,
        pose_threshold_default: float,
        pose_threshold_hip: float,
        pose_threshold_distal: float,
    ) -> None:
        """Load ONNX Runtime sessions and metadata."""
        self._pose_threshold_default = float(pose_threshold_default)
        self._pose_threshold_hip = float(pose_threshold_hip)
        self._pose_threshold_distal = float(pose_threshold_distal)

        movenet_path = _require_file(movenet_path, "MoveNet ONNX")
        reid_path = _require_file(reid_path, "PASS-ReID ONNX")
        promptpar_path = _require_file(promptpar_path, "PromptPAR ONNX")
        promptpar_attributes = _require_file(promptpar_attributes, "PromptPAR attributes")

        self._providers = _select_providers()
        self._movenet = _create_session(movenet_path, self._providers)
        self._reid = _create_session(reid_path, self._providers)
        self._promptpar = _create_session(promptpar_path, self._providers)

        self._movenet_input = _single_input_name(self._movenet, "MoveNet")
        self._movenet_output = _single_output_name(self._movenet, "MoveNet")
        self._movenet_size = _validate_input_meta(
            self._movenet,
            "MoveNet",
            expected_dtype="uint8",
            expected_channels=4,
            expected_layout="NHWC",
        )

        self._reid_input = _single_input_name(self._reid, "PASS-ReID")
        self._reid_output = _single_output_name(self._reid, "PASS-ReID")
        self._reid_size = _validate_input_meta(
            self._reid,
            "PASS-ReID",
            expected_dtype="float32",
            expected_channels=3,
            expected_layout="NCHW",
        )

        self._promptpar_input = _single_input_name(self._promptpar, "PromptPAR")
        self._promptpar_output = _single_output_name(self._promptpar, "PromptPAR")
        self._promptpar_size = _validate_input_meta(
            self._promptpar,
            "PromptPAR",
            expected_dtype="float32",
            expected_channels=3,
            expected_layout="NCHW",
        )

        self.embed_dim = _infer_reid_dim(self._reid, "PASS-ReID")
        self._promptpar_attributes = _load_attributes(promptpar_attributes)
        _validate_promptpar_outputs(self._promptpar, self._promptpar_attributes)

    def movenet(self, image: object) -> dict[str, object]:
        """Return pose gate details from MoveNet."""
        import numpy as np
        from PIL import Image

        if not isinstance(image, Image.Image):
            raise TypeError("movenet expects a PIL Image")
        rgba = image.convert("RGBA").resize(self._movenet_size, Image.BILINEAR)
        tensor = np.asarray(rgba, dtype=np.uint8)
        if tensor.shape != (self._movenet_size[1], self._movenet_size[0], 4):
            raise ValueError(f"MoveNet input shape mismatch: {tensor.shape}")
        output = self._movenet.run(
            [self._movenet_output],
            {self._movenet_input: tensor[None, ...]},
        )[0]
        if output.ndim != 4 or output.shape[-1] != 3:
            raise ValueError(f"Unexpected MoveNet output shape: {output.shape}")
        keypoints = output[0, 0]
        if keypoints.shape[0] != 17:
            raise ValueError(f"Unexpected MoveNet keypoint count: {keypoints.shape[0]}")
        keypoint_items = [
            {
                "index": int(idx),
                "x": float(point[1]),
                "y": float(point[0]),
                "score": float(point[2]),
            }
            for idx, point in enumerate(keypoints)
        ]
        return {
            "keypoints": keypoint_items,
            "threshold_default": self._pose_threshold_default,
            "threshold_hip": self._pose_threshold_hip,
            "threshold_distal": self._pose_threshold_distal,
        }

    def pass_reid(self, image: object) -> list[float]:
        """Return a normalized embedding from PASS-ReID."""
        import numpy as np
        from PIL import Image

        if not isinstance(image, Image.Image):
            raise TypeError("pass_reid expects a PIL Image")
        rgb = image.convert("RGB").resize(self._reid_size, Image.BILINEAR)
        tensor = np.asarray(rgb, dtype=np.float32) / 255.0
        tensor = (tensor - 0.5) / 0.5
        tensor = np.transpose(tensor, (2, 0, 1))
        output = self._reid.run(
            [self._reid_output],
            {self._reid_input: tensor[None, ...]},
        )[0]
        embedding = output.reshape(-1).astype(np.float32)
        if embedding.shape[0] != self.embed_dim:
            raise ValueError(f"Embedding dim mismatch: expected {self.embed_dim}, got {embedding.shape[0]}")
        norm = float(np.linalg.norm(embedding))
        if norm == 0.0:
            raise ValueError("PASS-ReID embedding norm is zero")
        embedding = embedding / (norm + 1e-12)
        return embedding.tolist()

    def promptpar(self, image: object) -> Mapping[str, object]:
        """Return PromptPAR attributes with probabilities."""
        import numpy as np
        from PIL import Image

        if not isinstance(image, Image.Image):
            raise TypeError("promptpar expects a PIL Image")
        rgb = image.convert("RGB").resize(self._promptpar_size, Image.BILINEAR)
        tensor = np.asarray(rgb, dtype=np.float32) / 255.0
        tensor = (tensor - 0.5) / 0.5
        tensor = np.transpose(tensor, (2, 0, 1))
        output = self._promptpar.run(
            [self._promptpar_output],
            {self._promptpar_input: tensor[None, ...]},
        )[0]
        probs = output.reshape(-1).astype(np.float32)
        if probs.shape[0] != len(self._promptpar_attributes):
            raise ValueError(
                f"PromptPAR output size mismatch: expected {len(self._promptpar_attributes)}, got {probs.shape[0]}"
            )
        return {name: float(score) for name, score in zip(self._promptpar_attributes, probs, strict=True)}


def _require_file(path: Path, label: str) -> Path:
    if not path.exists():
        raise FileNotFoundError(f"{label} not found: {path}")
    return path


def _select_providers() -> list[str]:
    try:
        import onnxruntime as ort
    except ImportError as exc:
        raise RuntimeError("onnxruntime is required for ONNX model inference") from exc
    available = ort.get_available_providers()
    preferred = ["CUDAExecutionProvider", "CPUExecutionProvider"]
    providers = [provider for provider in preferred if provider in available]
    if not providers:
        raise RuntimeError(f"No supported ONNX Runtime providers available. Available: {available}")
    return providers


def _create_session(path: Path, providers: Sequence[str]) -> object:
    import onnxruntime as ort

    return ort.InferenceSession(str(path), providers=list(providers))


def _single_input_name(session: object, label: str) -> str:
    inputs = session.get_inputs()
    if len(inputs) != 1:
        raise ValueError(f"{label} expects a single input, found {len(inputs)}")
    return inputs[0].name


def _single_output_name(session: object, label: str) -> str:
    outputs = session.get_outputs()
    if len(outputs) != 1:
        raise ValueError(f"{label} expects a single output, found {len(outputs)}")
    return outputs[0].name


def _validate_input_meta(
    session: object,
    label: str,
    *,
    expected_dtype: str,
    expected_channels: int,
    expected_layout: str,
) -> tuple[int, int]:
    meta = session.get_inputs()[0]
    shape = meta.shape
    if len(shape) != 4:
        raise ValueError(f"{label} input rank mismatch: expected 4, got {shape}")

    if expected_layout == "NHWC":
        batch, height, width, channels = shape
    elif expected_layout == "NCHW":
        batch, channels, height, width = shape
    else:
        raise ValueError(f"Unsupported expected layout: {expected_layout}")

    if isinstance(batch, int) and batch != 1:
        raise ValueError(f"{label} input batch mismatch: expected 1, got {shape}")
    if isinstance(channels, int) and channels != expected_channels:
        raise ValueError(f"{label} input channel mismatch: expected {expected_channels}, got {shape}")
    if not isinstance(height, int) or not isinstance(width, int):
        raise ValueError(f"{label} input spatial dims must be static integers: {shape}")
    if height <= 0 or width <= 0:
        raise ValueError(f"{label} input spatial dims must be positive: {shape}")

    type_str = str(meta.type)
    if expected_dtype == "uint8":
        if "uint8" not in type_str:
            raise ValueError(f"{label} input dtype mismatch: expected uint8, got {type_str}")
    elif expected_dtype == "float32":
        if "float16" in type_str or "float" not in type_str:
            raise ValueError(f"{label} input dtype mismatch: expected float32, got {type_str}")
    else:
        raise ValueError(f"Unsupported expected dtype: {expected_dtype}")
    return (width, height)


def _infer_reid_dim(session: object, label: str) -> int:
    outputs = session.get_outputs()
    if len(outputs) != 1:
        raise ValueError(f"{label} expects a single output, found {len(outputs)}")
    shape = outputs[0].shape
    if len(shape) != 2:
        raise ValueError(f"{label} output rank mismatch: expected 2, got {shape}")
    dim = shape[1]
    if not isinstance(dim, int):
        raise ValueError(f"{label} output embedding dimension is dynamic")
    return dim


def _load_attributes(path: Path) -> list[str]:
    labels = [line.strip() for line in path.read_text().splitlines() if line.strip()]
    if not labels:
        raise ValueError(f"No attribute labels found in {path}")
    return labels


def _validate_promptpar_outputs(session: object, labels: Sequence[str]) -> None:
    outputs = session.get_outputs()
    if len(outputs) != 1:
        raise ValueError(f"PromptPAR expects a single output, found {len(outputs)}")
    shape = outputs[0].shape
    if len(shape) != 2:
        raise ValueError(f"PromptPAR output rank mismatch: expected 2, got {shape}")
    output_dim = shape[1]
    if isinstance(output_dim, int) and output_dim != len(labels):
        raise ValueError(f"PromptPAR output dim {output_dim} does not match {len(labels)} labels")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_image(path: Path) -> object:
    try:
        from PIL import Image
    except ImportError as exc:
        raise RuntimeError("Pillow is required to load images") from exc
    with Image.open(path) as image:
        return image.convert("RGB")


def _apply_clahe_y(image: object) -> object:
    try:
        import cv2
        import numpy as np
        from PIL import Image
    except ImportError as exc:
        raise RuntimeError("opencv-python, numpy, and Pillow are required for clahe_y preprocessing") from exc
    if not isinstance(image, Image.Image):
        raise TypeError("clahe_y expects a PIL Image")
    rgb = np.asarray(image.convert("RGB"), dtype=np.uint8)
    if rgb.ndim != 3 or rgb.shape[2] != 3:
        raise ValueError(f"clahe_y input shape mismatch: {rgb.shape}")
    try:
        ycrcb = cv2.cvtColor(rgb, cv2.COLOR_RGB2YCrCb)
        y_channel, cr_channel, cb_channel = cv2.split(ycrcb)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        y_equalized = clahe.apply(y_channel)
        merged = cv2.merge((y_equalized, cr_channel, cb_channel))
        rgb_equalized = cv2.cvtColor(merged, cv2.COLOR_YCrCb2RGB)
    except Exception as exc:
        raise RuntimeError(f"clahe_y preprocessing failed: {exc}") from exc
    return Image.fromarray(rgb_equalized, mode="RGB")


def _normalize_embedding(embedding: Sequence[float]) -> list[float]:
    values = [float(value) for value in embedding]
    if not values:
        raise ValueError("Embedding is empty")
    norm = sum(value * value for value in values) ** 0.5
    if norm == 0.0:
        raise ValueError("Embedding norm is zero")
    return [value / (norm + 1e-12) for value in values]


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _parse_iso8601(value: object) -> datetime:
    if not isinstance(value, str) or not value:
        raise ValueError("timestamp is missing")
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _extract_quality(payload: Mapping[str, object]) -> float:
    if "quality_score" not in payload:
        raise ValueError("Qdrant payload.quality_score is missing")
    value = payload["quality_score"]
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("Qdrant payload.quality_score must be numeric") from exc


def _extract_updated_at(payload: Mapping[str, object]) -> datetime:
    if "updated_at" not in payload:
        raise ValueError("Qdrant payload.updated_at is missing")
    raw = payload.get("updated_at")
    return _parse_iso8601(raw)


def _estimate_sharpness(image: object) -> float:
    try:
        import cv2
        import numpy as np
        from PIL import Image
    except ImportError as exc:
        raise RuntimeError("opencv-python, numpy, and Pillow are required for sharpness estimation") from exc
    if not isinstance(image, Image.Image):
        raise TypeError("sharpness estimation expects a PIL Image")
    gray = cv2.cvtColor(np.asarray(image.convert("RGB"), dtype=np.uint8), cv2.COLOR_RGB2GRAY)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def _extract_pose_scores(pose_result: Mapping[str, object]) -> list[float]:
    keypoints = pose_result.get("keypoints")
    if not isinstance(keypoints, Sequence):
        raise ValueError("movenet result keypoints must be a sequence")
    if len(keypoints) != 17:
        raise ValueError(f"movenet result keypoints must have 17 entries, got {len(keypoints)}")

    scores: list[float] = [0.0] * 17
    for idx, keypoint in enumerate(keypoints):
        if not isinstance(keypoint, Mapping):
            raise ValueError("movenet keypoint entry must be a mapping")
        if "score" not in keypoint:
            raise ValueError("movenet keypoint.score is required")
        keypoint_index_obj = keypoint.get("index", idx)
        keypoint_index = int(keypoint_index_obj)
        if keypoint_index < 0 or keypoint_index >= 17:
            raise ValueError(f"movenet keypoint.index out of range: {keypoint_index}")
        scores[keypoint_index] = float(keypoint["score"])
    return scores


def _extract_pose_thresholds(
    pose_result: Mapping[str, object], cfg: Mapping[str, object]
) -> tuple[float, float, float]:
    if "threshold_default" in pose_result:
        threshold_default = float(pose_result["threshold_default"])
    else:
        threshold_default = float(cfg["pose_threshold_default"])
    if "threshold_hip" in pose_result:
        threshold_hip = float(pose_result["threshold_hip"])
    else:
        threshold_hip = float(cfg["pose_threshold_hip"])
    if "threshold_distal" in pose_result:
        threshold_distal = float(pose_result["threshold_distal"])
    else:
        threshold_distal = float(cfg["pose_threshold_distal"])
    return threshold_default, threshold_hip, threshold_distal


def _evaluate_pose_regions(
    scores: Sequence[float],
    threshold_default: float,
    threshold_hip: float,
    threshold_distal: float,
) -> tuple[dict[str, bool], list[str]]:
    if len(scores) != 17:
        raise ValueError(f"pose scores must have 17 entries, got {len(scores)}")
    region_head = max(scores[0], scores[1], scores[2], scores[3], scores[4]) >= threshold_default
    region_left_upper = max(scores[5], scores[7], scores[9]) >= threshold_default
    region_right_upper = max(scores[6], scores[8], scores[10]) >= threshold_default
    region_left_lower = (scores[11] >= threshold_hip) and (max(scores[13], scores[15]) >= threshold_distal)
    region_right_lower = (scores[12] >= threshold_hip) and (max(scores[14], scores[16]) >= threshold_distal)

    regions = {
        "head": region_head,
        "left_upper": region_left_upper,
        "right_upper": region_right_upper,
        "left_lower": region_left_lower,
        "right_lower": region_right_lower,
    }
    missing_regions = [name for name, passed in regions.items() if not passed]
    return regions, missing_regions


def _compute_pose_strength(scores: Sequence[float]) -> float:
    if len(scores) != 17:
        raise ValueError(f"pose scores must have 17 entries, got {len(scores)}")
    head_strength = max(scores[0], scores[1], scores[2], scores[3], scores[4])
    left_upper_strength = max(scores[5], scores[7], scores[9])
    right_upper_strength = max(scores[6], scores[8], scores[10])
    left_lower_strength = min(scores[11], max(scores[13], scores[15]))
    right_lower_strength = min(scores[12], max(scores[14], scores[16]))
    return float(
        (head_strength + left_upper_strength + right_upper_strength + left_lower_strength + right_lower_strength) / 5.0
    )


def _normalize_score_direction(value: object) -> str:
    if value is None:
        raise ValueError("score_direction is required")
    direction = str(value).lower()
    if direction in {"higher", "lower"}:
        return direction
    raise ValueError(f"Unsupported score_direction: {value}")


def _is_better_score(score: float, best_score: float | None, direction: str) -> bool:
    if best_score is None:
        return True
    if direction == "higher":
        return score > best_score
    return score < best_score


def _is_match_score(score: float, t_match: float, direction: str) -> bool:
    if direction == "higher":
        return score >= t_match
    return score <= t_match


def _is_new_score(score: float, t_new: float, direction: str) -> bool:
    if direction == "higher":
        return score < t_new
    return score > t_new


def _sort_scores(scores: list[float], direction: str) -> list[float]:
    reverse = direction == "higher"
    return sorted(scores, reverse=reverse)


def _aggregate_person_scores(
    search_results: list[dict[str, object]],
    *,
    top_n: int,
    direction: str,
) -> tuple[dict[str, float], dict[str, float]]:
    grouped: dict[str, list[float]] = {}
    best_prototype_score: dict[str, float] = {}
    for item in search_results:
        score_obj = item.get("score")
        payload_obj = item.get("payload")
        if score_obj is None:
            raise ValueError("Qdrant result score is missing")
        if not isinstance(payload_obj, Mapping):
            raise ValueError("Qdrant result payload is missing")
        person_obj = payload_obj.get("person_id")
        if not isinstance(person_obj, str) or not person_obj:
            raise ValueError("Qdrant result payload.person_id is missing")
        score = float(score_obj)
        grouped.setdefault(person_obj, []).append(score)
        best = best_prototype_score.get(person_obj)
        if _is_better_score(score, best, direction):
            best_prototype_score[person_obj] = score

    person_scores: dict[str, float] = {}
    for person_id, scores in grouped.items():
        ordered = _sort_scores(scores, direction)
        selected = ordered[:top_n]
        person_scores[person_id] = sum(selected) / float(len(selected))
    return person_scores, best_prototype_score


def _best_and_second_person(
    person_scores: Mapping[str, float],
    direction: str,
) -> tuple[str | None, float | None, float | None]:
    best_person: str | None = None
    best_score: float | None = None
    second_score: float | None = None
    for person_id, score in person_scores.items():
        if _is_better_score(score, best_score, direction):
            second_score = best_score
            best_person = person_id
            best_score = score
            continue
        if _is_better_score(score, second_score, direction):
            second_score = score
    return best_person, best_score, second_score


def _score_margin(best: float | None, second: float | None, direction: str) -> float:
    if best is None:
        return 0.0
    if second is None:
        return 1.0
    if direction == "higher":
        return max(0.0, best - second)
    return max(0.0, second - best)


def _build_result(
    *,
    path: Path,
    sha256: str,
    pose_ok: bool,
    threshold_default: float,
    threshold_hip: float,
    threshold_distal: float,
    region_head: bool,
    region_left_upper: bool,
    region_right_upper: bool,
    region_left_lower: bool,
    region_right_lower: bool,
    missing_regions: Sequence[str],
    embed_dim: int,
) -> dict[str, object]:
    return {
        "input": {"image_path": str(path), "sha256": sha256},
        "pose": {
            "pose_ok": pose_ok,
            "threshold_default": threshold_default,
            "threshold_hip": threshold_hip,
            "threshold_distal": threshold_distal,
            "region_head": region_head,
            "region_left_upper": region_left_upper,
            "region_right_upper": region_right_upper,
            "region_left_lower": region_left_lower,
            "region_right_lower": region_right_lower,
            "missing_regions": list(missing_regions),
        },
        "reid": {
            "embedding_dim": embed_dim,
            "match_score": None,
            "global_person_id": None,
            "is_new_person": None,
            "decision_reason": "not_evaluated",
        },
        "par": {"ran": False, "attributes": {}},
        "errors": [],
    }


def _get_embedding(models: ModelsProtocol, image_input: object, embed_dim: int) -> list[float]:
    embedding = models.pass_reid(image_input)
    if not isinstance(embedding, list):
        embedding = list(embedding)
    if len(embedding) != embed_dim:
        raise ValueError(f"Embedding dim mismatch: expected {embed_dim}, got {len(embedding)}")
    return embedding


def _resolve_match(
    qdrant: QdrantClientProtocol,
    embedding: list[float],
    search_k: int,
    person_score_top_n: int,
    t_match: float,
    t_new: float | None,
    score_direction: str,
) -> tuple[str | None, float | None, bool | None, str, float, float | None]:
    direction = _normalize_score_direction(score_direction)
    search_results = qdrant.search(embedding=embedding, top_k=search_k, with_payload=True)
    if not isinstance(search_results, list):
        raise ValueError("Qdrant search must return a list")
    person_scores, prototype_best = _aggregate_person_scores(
        search_results,
        top_n=person_score_top_n,
        direction=direction,
    )
    best_id, best_score, second_best_score = _best_and_second_person(person_scores, direction)
    best_proto_score = None if best_id is None else prototype_best.get(best_id)
    margin = _score_margin(best_score, second_best_score, direction)
    if best_score is None:
        return None, None, True, "no_candidates_create_new", margin, best_proto_score
    if _is_match_score(best_score, t_match, direction):
        return best_id, best_score, False, "matched_existing_topn_avg", margin, best_proto_score
    if t_new is None or _is_new_score(best_score, t_new, direction):
        return best_id, best_score, True, "below_t_new_create_new", margin, best_proto_score
    return best_id, best_score, None, "uncertain_between_t_match_t_new", margin, best_proto_score


def _update_reid(
    result: dict[str, object],
    *,
    match_score: float | None,
    global_person_id: str | None,
    is_new_person: bool | None,
    decision_reason: str,
    embedding: list[float] | None,
    save_embedding: bool,
) -> None:
    reid = result.get("reid")
    if not isinstance(reid, dict):
        raise ValueError("Invalid reid payload")
    reid["match_score"] = match_score
    reid["global_person_id"] = global_person_id
    reid["is_new_person"] = is_new_person
    reid["decision_reason"] = decision_reason
    if save_embedding and embedding is not None:
        reid["embedding"] = embedding


def _compute_quality_score(
    *,
    pose_strength: float,
    sharpness: float,
    margin: float,
    cfg: Mapping[str, object],
) -> float:
    pose_ratio = _clamp(float(pose_strength), 0.0, 1.0)
    sharpness_ref = max(float(cfg["quality_sharpness_ref"]), 1e-6)
    sharpness_ratio = _clamp(sharpness / sharpness_ref, 0.0, 1.0)
    margin_ref = max(float(cfg["prototype_min_margin"]), 0.05)
    margin_ratio = _clamp(margin / margin_ref, 0.0, 1.0)
    pose_weight = float(cfg["quality_pose_weight"])
    sharpness_weight = float(cfg["quality_sharpness_weight"])
    margin_weight = float(cfg["quality_margin_weight"])
    return _clamp(
        (pose_weight * pose_ratio) + (sharpness_weight * sharpness_ratio) + (margin_weight * margin_ratio), 0.0, 1.0
    )


def _is_redundant_prototype(score: float, threshold: float, direction: str) -> bool:
    if direction == "higher":
        return score >= threshold
    return score <= threshold


def _insert_prototype_point(
    *,
    qdrant: QdrantClientProtocol,
    person_id: str,
    embedding: list[float],
    quality_score: float,
    now: datetime,
) -> str:
    prototype_id = str(uuid.uuid4())
    now_iso = now.isoformat(timespec="milliseconds")
    payload = {
        "person_id": person_id,
        "quality_score": quality_score,
        "created_at": now_iso,
        "updated_at": now_iso,
        "seen_count": 1,
    }
    qdrant.upsert(id=prototype_id, embedding=embedding, payload=payload)
    return prototype_id


def _maybe_store_prototype(
    *,
    qdrant: QdrantClientProtocol,
    person_id: str,
    embedding: list[float],
    quality_score: float,
    margin: float,
    best_prototype_score: float | None,
    cfg: Mapping[str, object],
    now: datetime,
    direction: str,
) -> tuple[bool, str]:
    def _require_payload(point: Mapping[str, object]) -> Mapping[str, object]:
        payload_obj = point.get("payload")
        if not isinstance(payload_obj, Mapping):
            raise ValueError("Qdrant point payload is missing")
        return payload_obj

    person_points = qdrant.list_person_points(person_id=person_id)
    if not person_points:
        _insert_prototype_point(
            qdrant=qdrant,
            person_id=person_id,
            embedding=embedding,
            quality_score=quality_score,
            now=now,
        )
        return True, "prototype_seed_inserted"

    if quality_score < float(cfg["prototype_min_quality"]):
        return False, "prototype_quality_below_min"
    if margin < float(cfg["prototype_min_margin"]):
        return False, "prototype_margin_below_min"
    if best_prototype_score is not None and _is_redundant_prototype(
        best_prototype_score,
        float(cfg["prototype_similarity_redundancy_threshold"]),
        direction,
    ):
        return False, "prototype_redundant_similarity"
    if person_points:
        latest = max(_extract_updated_at(_require_payload(point)) for point in person_points)
        elapsed_sec = (now - latest).total_seconds()
        if elapsed_sec < float(cfg["prototype_min_interval_sec"]):
            return False, "prototype_min_interval_not_met"

    prototype_id = _insert_prototype_point(
        qdrant=qdrant,
        person_id=person_id,
        embedding=embedding,
        quality_score=quality_score,
        now=now,
    )

    max_per_person = int(cfg["prototype_max_per_person"])
    if len(person_points) + 1 <= max_per_person:
        return True, "prototype_inserted"

    now_iso = now.isoformat(timespec="milliseconds")
    new_payload = {
        "person_id": person_id,
        "quality_score": quality_score,
        "created_at": now_iso,
        "updated_at": now_iso,
        "seen_count": 1,
    }
    points_with_new = [*person_points, {"id": prototype_id, "payload": new_payload}]
    policy = str(cfg["prototype_eviction_policy"]).strip().lower()
    if policy != "lowest_quality_then_oldest":
        raise ValueError(f"unsupported prototype_eviction_policy: {cfg['prototype_eviction_policy']}")

    sorted_points = sorted(
        points_with_new,
        key=lambda item: (
            _extract_quality(_require_payload(item)),
            _extract_updated_at(_require_payload(item)),
        ),
    )
    overflow = len(points_with_new) - max_per_person
    evict_ids = [str(item["id"]) for item in sorted_points[:overflow]]
    qdrant.delete_points(ids=evict_ids)
    return True, "prototype_inserted_with_eviction"


def analyze_patch(
    *,
    image_path: Path | str,
    qdrant: QdrantClientProtocol,
    models: ModelsProtocol,
    config: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Run pose gate, re-id, Qdrant lookup, and optional PromptPAR."""
    if config is None:
        raise KeyError("config")
    cfg = dict(config)
    embed_dim = int(cfg["embed_dim"])
    search_k = int(cfg["prototype_search_k"])
    person_score_top_n = int(cfg["prototype_person_score_top_n"])
    score_direction = _normalize_score_direction(cfg["score_direction"])
    path = Path(image_path)
    if not path.exists():
        raise FileNotFoundError(f"Image not found: {path}")

    sha256 = _sha256(path)

    if getattr(models, "expects_image", False):
        raw_image = _load_image(path)
        image_input: object = _apply_clahe_y(raw_image)
    else:
        image_input = path

    pose_result = models.movenet(image_input)
    if not isinstance(pose_result, Mapping):
        raise ValueError("movenet must return a mapping")

    pose_scores = _extract_pose_scores(pose_result)
    threshold_default, threshold_hip, threshold_distal = _extract_pose_thresholds(pose_result, cfg)
    regions, missing_regions = _evaluate_pose_regions(
        pose_scores,
        threshold_default,
        threshold_hip,
        threshold_distal,
    )
    pose_ok = len(missing_regions) == 0
    pose_gate_failed = not pose_ok

    result = _build_result(
        path=path,
        sha256=sha256,
        pose_ok=pose_ok,
        threshold_default=threshold_default,
        threshold_hip=threshold_hip,
        threshold_distal=threshold_distal,
        region_head=regions["head"],
        region_left_upper=regions["left_upper"],
        region_right_upper=regions["right_upper"],
        region_left_lower=regions["left_lower"],
        region_right_lower=regions["right_lower"],
        missing_regions=missing_regions,
        embed_dim=embed_dim,
    )

    embedding = _get_embedding(models, image_input, embed_dim)
    t_new_value = cfg["t_new"]
    t_new = None if t_new_value is None else float(t_new_value)
    best_id, best_score, is_new_person, decision_reason, margin, best_prototype_score = _resolve_match(
        qdrant,
        embedding,
        search_k,
        person_score_top_n,
        float(cfg["t_match"]),
        t_new,
        score_direction,
    )

    if is_new_person is True:
        global_person_id = str(uuid.uuid4())
    elif is_new_person is False:
        global_person_id = best_id
    else:
        global_person_id = None
    was_uncertain = is_new_person is None
    if pose_gate_failed and global_person_id is None:
        global_person_id = str(uuid.uuid4())
        is_new_person = True
        decision_reason = f"pose_gate_failed:{decision_reason}:forced_new_id"
    elif pose_gate_failed:
        decision_reason = f"pose_gate_failed:{decision_reason}"
    _update_reid(
        result,
        match_score=best_score,
        global_person_id=global_person_id,
        is_new_person=is_new_person,
        decision_reason=decision_reason,
        embedding=embedding,
        save_embedding=bool(cfg.get("save_embedding")),
    )
    reid = result.get("reid")
    if not isinstance(reid, dict):
        raise ValueError("Invalid reid payload")
    reid["memory_updated"] = False
    reid["quality_score"] = None
    reid["match_margin"] = margin

    errors = result.get("errors")
    if not isinstance(errors, list):
        errors = []
        result["errors"] = errors
    if was_uncertain:
        errors.append("reid_uncertain_band")

    par_attributes_for_profile: dict[str, object] | None = None
    if pose_gate_failed:
        result["par"] = None
    elif is_new_person is True and global_person_id:
        par_attributes_for_profile = dict(models.promptpar(image_input))
        result["par"] = {"ran": True, "attributes": par_attributes_for_profile}
    elif is_new_person is False and global_person_id:
        cached_par_attributes = qdrant.get_person_profile_par(person_id=str(global_person_id))
        if cached_par_attributes is None:
            par_attributes_for_profile = dict(models.promptpar(image_input))
            result["par"] = {"ran": True, "attributes": par_attributes_for_profile}
        else:
            result["par"] = {"ran": False, "attributes": cached_par_attributes}

    now = datetime.now(timezone.utc)
    if not pose_gate_failed and global_person_id and par_attributes_for_profile is not None:
        try:
            qdrant.upsert_person_profile_par(
                person_id=str(global_person_id),
                embedding=embedding,
                par_attributes=par_attributes_for_profile,
                now=now,
            )
        except Exception as exc:
            errors.append(f"par_profile_upsert_failed:{exc}")

    sharpness = _estimate_sharpness(image_input)
    pose_strength = _compute_pose_strength(pose_scores)
    quality_score = _compute_quality_score(
        pose_strength=pose_strength,
        sharpness=sharpness,
        margin=margin,
        cfg=cfg,
    )
    reid["quality_score"] = quality_score

    if is_new_person is not None and global_person_id:
        try:
            memory_updated, store_reason = _maybe_store_prototype(
                qdrant=qdrant,
                person_id=str(global_person_id),
                embedding=embedding,
                quality_score=quality_score,
                margin=margin,
                best_prototype_score=best_prototype_score,
                cfg=cfg,
                now=now,
                direction=score_direction,
            )
            reid["memory_updated"] = memory_updated
            if (
                store_reason != "prototype_inserted"
                and store_reason != "prototype_inserted_with_eviction"
                and store_reason != "prototype_seed_inserted"
            ):
                reid["decision_reason"] = f"{decision_reason}:{store_reason}"
        except Exception as exc:
            errors.append(f"reid_memory_update_failed:{exc}")

    return result


def build_qdrant_adapter(
    qdrant_url: str, collection: str, person_profile_collection: str
) -> QdrantClientProtocol:
    """Create a thin adapter over the Qdrant client."""
    from qdrant_client import QdrantClient
    from qdrant_client.http import models as rest

    try:
        client = QdrantClient(url=qdrant_url, check_compatibility=False)
    except TypeError:
        client = QdrantClient(url=qdrant_url)
    return QdrantAdapter(client, collection, person_profile_collection, rest)


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze a person patch and write JSON output.")
    parser.add_argument("--image", required=True, help="Input image path")
    parser.add_argument("--out", required=True, help="Output JSON path")
    parser.add_argument("--qdrant-url", required=True, help="Qdrant base URL")
    parser.add_argument("--collection", required=True, help="Qdrant collection")
    parser.add_argument("--person-profile-collection", required=True, help="Qdrant person profile collection")
    parser.add_argument("--t-match", type=float, required=True, help="Match threshold")
    parser.add_argument("--t-new", type=float, help="New-person threshold")
    parser.add_argument(
        "--score-direction",
        choices=["higher", "lower"],
        required=True,
        help="Score direction for Qdrant (higher|lower)",
    )
    parser.add_argument(
        "--embed-dim",
        type=int,
        required=True,
        help="Embedding dimension",
    )
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
    parser.add_argument(
        "--prototype-max-per-person",
        type=int,
        required=True,
        help="Max prototype points per person id",
    )
    parser.add_argument(
        "--prototype-search-k",
        type=int,
        required=True,
        help="Prototype search top-k size",
    )
    parser.add_argument(
        "--prototype-person-score-top-n",
        type=int,
        required=True,
        help="Top-n prototypes used to aggregate person score",
    )
    parser.add_argument(
        "--prototype-min-quality",
        type=float,
        required=True,
        help="Minimum quality score to store a prototype",
    )
    parser.add_argument(
        "--prototype-min-margin",
        type=float,
        required=True,
        help="Minimum person score margin to store a prototype",
    )
    parser.add_argument(
        "--prototype-min-interval-sec",
        type=float,
        required=True,
        help="Minimum seconds between prototype inserts for the same person",
    )
    parser.add_argument(
        "--prototype-similarity-redundancy-threshold",
        type=float,
        required=True,
        help="Skip insert when best prototype similarity is above this threshold",
    )
    parser.add_argument(
        "--prototype-eviction-policy",
        required=True,
        choices=["lowest_quality_then_oldest"],
        help="Prototype eviction policy",
    )
    parser.add_argument(
        "--quality-pose-weight",
        type=float,
        required=True,
        help="Pose score weight for prototype quality",
    )
    parser.add_argument(
        "--quality-sharpness-weight",
        type=float,
        required=True,
        help="Sharpness score weight for prototype quality",
    )
    parser.add_argument(
        "--quality-margin-weight",
        type=float,
        required=True,
        help="Match margin weight for prototype quality",
    )
    parser.add_argument(
        "--quality-sharpness-ref",
        type=float,
        required=True,
        help="Reference sharpness value used for normalization",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    """CLI entrypoint for the patch analyzer."""
    args = _parse_args(argv)
    config = {
        "t_match": args.t_match,
        "t_new": args.t_new,
        "save_embedding": args.save_embedding,
        "score_direction": args.score_direction,
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
        raise ValueError(f"--embed-dim {args.embed_dim} does not match model output {models.embed_dim}")
    config["embed_dim"] = models.embed_dim

    qdrant = build_qdrant_adapter(args.qdrant_url, args.collection, args.person_profile_collection)

    result = analyze_patch(
        image_path=Path(args.image),
        qdrant=qdrant,
        models=models,
        config=config,
    )

    Path(args.out).write_text(json.dumps(result, indent=2, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
