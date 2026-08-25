# Implementation Plan (Core Only): `gst-lliefilter` for DeepStream 8.0 (dGPU)

## Status

- [x] Base folder `runtime/worker-node/mantis-node-manager/elements/gst-lliefilter` created with Makefile and skeleton sources (`gstlliefilter.cpp`, `gstlliefilter.h`, `trt_filter_preprocess.cu`, `trt_filter_postprocess.cu`).
- [x] Boilerplate wired: TensorRT lifecycle scaffolded (engine load, bindings alloc, CUDA stream), in-place transform flow stubbed with preprocess/infer/postprocess hooks, Makefile builds CUDA stubs and links TensorRT.

## 1. Goal

Create a DeepStream 8.0 **dGPU** GStreamer plugin `gst-lliefilter` that:

- Runs a **TensorRT** image-to-image model per frame.
- Reads an NVMM `NvBufSurface` frame.
- Writes the **model output back to the same frame (in-place)**.
- Is usable in pipelines like:

  ```bash
  ... ! nvstreammux ! nvvideoconvert ! lliefilter \
        engine-path=/models/filter.engine gpu-id=0 ! \
        nvvideoconvert ! nveglglessink

(Architecture follows NVIDIA’s gst-dsexample custom plugin pattern in DeepStream SDK.)

⸻

2. Mandatory Plugin Interface

2.1 Element & files

- Element name: lliefilter
- GObject type: Gstlliefilter
- Shared object: libnvdsgst_lliefilter.so
- Files (minimal):

gst-lliefilter/
  Makefile
  gstlliefilter.cpp
  gstlliefilter.h
  trt_filter_preprocess.cu
  trt_filter_postprocess.cu

2.2 Properties (no optionals)

- engine-path (string, required): path to serialized TensorRT .engine.
- gpu-id (int, required): GPU index.

If either is missing/invalid at start(), fail the plugin (return FALSE, log error).

⸻

3. Core Dataflow (Per Frame)
1. Get NvBufSurface* from GstBuffer.
2. For each batch element:

- Map surface (READ_WRITE).
- Preprocess: NV12/RGBA → float32 NCHW in TensorRT input buffer.
- Run TensorRT: enqueueV3() on plugin CUDA stream.
- Postprocess: TensorRT output → overwrite same NvBufSurface pixels.
- Unmap and sync for device.

 3. Return GST_FLOW_OK only on success; on error, return error and log (no silent pass-through).

⸻

4. Implementation Steps

Step 1. Clone and rebrand gst-dsexample

 1. From DeepStream 8.0 sources:

cd /opt/nvidia/deepstream/deepstream-8.0/sources/gst-plugins
cp -r gst-dsexample gst-lliefilter

 2. Rename:

- gstdsexample.cpp → gstlliefilter.cpp
- gstdsexample.h → gstlliefilter.h
- All GstDsExample → Gstlliefilter
- All gst_dsexample_*→ gst_lliefilter_*
- Plugin metadata strings → “TensorRT Bitmap Filter”.

 3. Update Makefile:

- Target: libnvdsgst_lliefilter.so
- Keep DeepStream include paths (nvbufsurface.h, gstnvdsmeta.h, etc.).

 4. Build & verify:

make
gst-inspect-1.0 lliefilter

⸻

Step 2. Add TensorRT state & lifecycle

2.1 Struct fields
In gstlliefilter.h:

# include "NvInfer.h"

typedef struct _Gstlliefilter {
  GstBaseTransform parent;

  guint gpu_id;
  gchar* engine_path;

  cudaStream_t cuda_stream;
  nvinfer1::IRuntime*runtime;
  nvinfer1::ICudaEngine* engine;
  nvinfer1::IExecutionContext* context;

  int inputIndex;
  int outputIndex;
  nvinfer1::Dims inputDims;
  nvinfer1::Dims outputDims;

  void* bindings[2];       // [inputIndex], [outputIndex]
  size_t inputSizeBytes;
  size_t outputSizeBytes;

  guint frame_width;
  guint frame_height;
} Gstlliefilter;

2.2 Properties
In gst_lliefilter_class_init():

- Register engine-path (string, must be non-null).
- Register gpu-id (int, default 0, but treated as required for clarity).

2.3 start() / stop()
In gst_lliefilter_start():

 1. Validate engine_path and GPU ID. If invalid → log error and return FALSE.
 2. cudaSetDevice(gpu-id).
 3. cudaStreamCreate(&cuda_stream).
 4. Read engine file (binary) into memory.
 5. runtime = createInferRuntime(...).
 6. engine = runtime->deserializeCudaEngine(...).
 7. context = engine->createExecutionContext().
 8. Query bindings:

- inputIndex = engine->getBindingIndex("input") (or index 0).
- outputIndex = engine->getBindingIndex("output") (or index 1).
- inputDims = engine->getBindingDimensions(inputIndex).
- outputDims = engine->getBindingDimensions(outputIndex).

 9. Compute inputSizeBytes / outputSizeBytes and allocate cudaMalloc for bindings[inputIndex] and bindings[outputIndex].
 10. Return TRUE only on complete success.

In gst_lliefilter_stop():

- cudaFree for both bindings.
- Destroy context, engine, runtime.
- Destroy cuda_stream.

⸻

Step 3. Caps & NvBufSurface access

3.1 Caps
In pad templates:

- Sink/src caps:

"video/x-raw(memory:NVMM), format=NV12; "
"video/x-raw(memory:NVMM), format=RGBA"

In gst_lliefilter_set_caps():

- Read width, height, format from incaps.
- Save into frame_width, frame_height.
- Optionally assert compatibility with inputDims (e.g. same or known-resize).

3.2 Mapping frame
In gst_lliefilter_transform_ip():

NvBufSurface*surface =
  (NvBufSurface*) gst_buffer_get_nvds_surface (buf);

for (guint i = 0; i < surface->batchSize; ++i) {
  NvBufSurfaceMap(surface, i, 0, NVBUF_MAP_READ_WRITE);
  NvBufSurfaceSyncForCpu(surface, i, 0);

  NvBufSurfaceParams* params = &surface->surfaceList[i];

  // Preprocess + TRT + Postprocess (see Step 4)

  NvBufSurfaceSyncForDevice(surface, i, 0);
  NvBufSurfaceUnMap(surface, i, 0);
}

On any CUDA/TensorRT failure, log with GST_ERROR_OBJECT and return an error flow (no silent success).

⸻

Step 4. Preprocess → TensorRT → Postprocess

4.1 Preprocess kernel
trt_filter_preprocess.cu:

- Kernel input: uint8_t*src (NV12 or RGBA), width/height, pitch.
- Kernel output: float* dst (NCHW).
- Responsibilities:
- Color conversion (e.g. NV12/ RGBA → RGB).
- Resize (if needed) to inputDims.
- Normalize to float.

Called from transform_ip():

launch_preprocess_kernel(
  (uint8_t*)params->dataPtr,
  (float*)filter->bindings[filter->inputIndex],
  params->width, params->height,
  filter->inputDims.d[2], filter->inputDims.d[3],
  filter->cuda_stream);

4.2 TensorRT inference

filter->context->enqueueV3(
  filter->cuda_stream,
  filter->bindings,
  nullptr);

4.3 Postprocess kernel
trt_filter_postprocess.cu:

- Kernel input: float*src (TRT output).
- Kernel output: uint8_t* dst (same NVMM surface).
- Responsibilities:
- Map model output to image pixels (scale, clamp).
- Resize if outputDims differ from frame size.
- Write directly into params->dataPtr (NV12/ RGBA layout).

Called from transform_ip():

launch_postprocess_kernel(
  (float*)filter->bindings[filter->outputIndex],
  (uint8_t*)params->dataPtr,
  filter->outputDims.d[2], filter->outputDims.d[3],
  params->width, params->height,
  filter->cuda_stream);

⸻

5. Build & Test (Minimal)
1. Build plugin in DeepStream 8.0 env:

cd /opt/nvidia/deepstream/deepstream-8.0/sources/gst-plugins/gst-lliefilter
make
sudo cp libnvdsgst_lliefilter.so /opt/nvidia/deepstream/deepstream-8.0/lib/gst-plugins/
gst-inspect-1.0 lliefilter

 2. Test with a simple pipeline:

gst-launch-1.0 \
  filesrc location=sample.h264 ! h264parse ! nvv4l2decoder ! \
  nvstreammux name=mux batch-size=1 width=1280 height=720 ! \
  lliefilter engine-path=/models/filter.engine gpu-id=0 ! \
  nvvideoconvert ! nveglglessink

- If any critical init or runtime error occurs, the plugin must fail loudly (log + error return), not fall back to no-op.

⸻
