# Object Detection Async Kafka Element

This element mirrors the existing `object_detection` video branch and adds an async metadata branch that
publishes per-object patch events to Kafka. The metadata path never blocks the video pipeline.

Kafka publishing is required. If `kafka.enabled` is false, the element fails fast.

## Config

Provide the element config via `--config-file <path-to-json>`. Required fields:

- `input_url` (string)

Optional fields (defaults shown):

- `infer_config_path` (`/opt/mantis/runtime/elements/object_detection/configs/primary_infer_config.txt`)
- `tracker_config_path` (`/opt/mantis/runtime/elements/object_detection/configs/primary_tracker_config.txt`)
- `tracker_lib_path` (`/opt/nvidia/deepstream/deepstream/lib/libnvds_nvmultiobjecttracker.so`)
- `moth_config_path` (`/opt/mantis/runtime/config_tcp.txt`)
- `latency_ms` (200)
- `use_tcp` (true)
- `batch_size` (1)
- `streammux_width` (1920)
- `streammux_height` (1080)
- `gpu_id` (0)
- `nvbuf_memory_type` (0)
- `confidence_threshold` (0.5)
- `emit_empty_frames` (false)
- `labels` ([])
- `label_file` (`/opt/mantis/runtime/model_repository/rtdetr_trt/labels.txt`)
- `video_output` (true)
- `video_bitrate` (2000000)
- `osd_enable` (true)
- `stream_id` ("")
- `type` ("")

Async queue:

- `async_queue_size` (256)
- `appsink_max_buffers` (2)

Patch export nested config:

- `patch.enabled` (required)
- `patch.labels` (`["person"]`)
- `patch.class_ids` (`[]`)
- `patch.confidence_threshold` (defaults to `confidence_threshold`)
- `patch.max_objects_per_frame` (50)
- `patch.sampling_interval_ms` (0)
- `patch.sampling_interval_frames` (0)
- `patch.min_interval_ms_per_tracking_id` (250)
- `patch.size` (optional resize; integer max-side or `[width, height]`)
- `patch.jpeg_quality` (85)
- `patch.message_max_bytes` (512000)

`patch.enabled` requires `kafka.enabled=true`.

Kafka nested config:

- `kafka.enabled` (required)
- `kafka.bootstrap_servers` (required)
- `kafka.topic` (`mantis.person.patch.events.v1`)
- `kafka.client_id` (required)
- `kafka.acks` (`1`)
- `kafka.compression` (`lz4`)
- `kafka.linger_ms` (5)
- `kafka.batch_num_messages` (1000)
- `kafka.message_timeout_ms` (2000)
- `kafka.queue_buffering_max_kbytes` (102400)
- `kafka.max_in_flight` (5)

When Kafka is enabled, `stream_id` must be set so message keys are stable.

## Kafka event schema (v1)

Each message is a single object patch.

```json
{
  "version": "v1",
  "event_id": "uuid",
  "stream_id": "4f57f2d1-9f09-47fc-9652-6af876d3d2ec",
  "frame_id": 123,
  "timestamp_ns": 1234567890,
  "object": {
    "class_id": 0,
    "label": "person",
    "tracking_id": 42,
    "confidence": 0.92,
    "bbox": { "left": 10.0, "top": 20.0, "width": 80.0, "height": 160.0 }
  },
  "patch": {
    "format": "jpeg",
    "width": 128,
    "height": 256,
    "bytes_b64": "..."
  },
  "meta": {
    "source": "reid",
    "element_version": "1.0.0",
    "sampling_interval_ms": 0
  }
}
```
