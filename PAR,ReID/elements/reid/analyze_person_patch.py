"""Entry point and compatibility facade for person patch analysis."""

import sys

from .analyzer import service as _service

OnnxModels = _service.OnnxModels
QdrantAdapter = _service.QdrantAdapter
build_qdrant_adapter = _service.build_qdrant_adapter

_load_image = _service._load_image
_apply_clahe_y = _service._apply_clahe_y
_estimate_sharpness = _service._estimate_sharpness


def analyze_patch(*args, **kwargs):
    return _service.analyze_patch(*args, **kwargs)


def main(argv):
    return _service.main(argv)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
