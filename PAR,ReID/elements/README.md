# Mantis Elements

This directory contains all processing elements for the Mantis media processing pipeline.

## Elements

- **passthrough/** - RTSP passthrough source that emits encoded H.264/H.265 frames.
- **llie/** - Low-Light Image Enhancement (LLIE) pipeline element.
- **llie_object_detection/** - LLIE + object detection combined pipeline.
- **object_detection/** - DeepStream object detection element.
- **reid/** - ReID element with async metadata branch that publishes per-object patches to Kafka/MQTT.
- **gst-lliefilter/** - GStreamer plugin used by LLIE pipelines.

## Element Interface

All elements follow a standardized interface:

- Launched as independent processes via `os.exec`
- Configuration passed via stdio arguments
- ZeroMQ sockets for data channels
- Separate control channel for health/stats reporting

## Implementation Languages

- **C++ Elements**: passthrough, llie, llie_object_detection, object_detection, reid, gst-lliefilter
