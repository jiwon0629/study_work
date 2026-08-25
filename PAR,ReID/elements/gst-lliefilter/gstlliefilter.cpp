/*
 * SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: LicenseRef-NvidiaProprietary
 *
 * NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
 * property and proprietary rights in and to this material, related
 * documentation and any modifications thereto. Any use, reproduction,
 * disclosure or distribution of this material and related documentation
 * without an express license agreement from NVIDIA CORPORATION or
 * its affiliates is strictly prohibited.
 */

#include <string.h>

#include <fstream>
#include <numeric>
#include <vector>
#include <stdint.h>

#include "gstlliefilter.h"

GST_DEBUG_CATEGORY_STATIC (gst_lliefilter_debug);
#define GST_CAT_DEFAULT gst_lliefilter_debug

enum
{
  PROP_0,
  PROP_ENGINE_PATH,
  PROP_GPU_ID,
};

#define GST_CAPS_FEATURE_MEMORY_NVMM "memory:NVMM"

static GstStaticPadTemplate gst_lliefilter_sink_template =
    GST_STATIC_PAD_TEMPLATE ("sink", GST_PAD_SINK, GST_PAD_ALWAYS,
        GST_STATIC_CAPS (GST_VIDEO_CAPS_MAKE_WITH_FEATURES
            (GST_CAPS_FEATURE_MEMORY_NVMM, "{ NV12, RGBA }")));

static GstStaticPadTemplate gst_lliefilter_src_template =
    GST_STATIC_PAD_TEMPLATE ("src", GST_PAD_SRC, GST_PAD_ALWAYS,
        GST_STATIC_CAPS (GST_VIDEO_CAPS_MAKE_WITH_FEATURES
            (GST_CAPS_FEATURE_MEMORY_NVMM, "{ NV12, RGBA }")));

#define gst_lliefilter_parent_class parent_class
G_DEFINE_TYPE (Gstlliefilter, gst_lliefilter, GST_TYPE_BASE_TRANSFORM);

namespace {

class TrtLogger : public nvinfer1::ILogger
{
public:
  void log (Severity severity, const char *msg) noexcept override
  {
    if (severity <= Severity::kWARNING) {
      GST_ERROR ("[TRT] %s", msg);
    } else {
      GST_DEBUG ("[TRT] %s", msg);
    }
  }
};

TrtLogger g_trt_logger;

size_t
dims_volume (const nvinfer1::Dims &dims)
{
  return std::accumulate (dims.d, dims.d + dims.nbDims, static_cast<size_t> (1),
      [] (size_t a, int64_t b) { return a * static_cast<size_t> (b > 0 ? b : 1); });
}

bool
load_engine (const gchar *path, std::vector<char> &data, Gstlliefilter *filter)
{
  std::ifstream f (path, std::ios::binary | std::ios::ate);
  if (!f.good ()) {
    GST_ERROR_OBJECT (filter, "failed to open engine file: %s", path);
    return false;
  }
  std::streamsize size = f.tellg ();
  f.seekg (0, std::ios::beg);
  data.resize (static_cast<size_t> (size));
  if (!f.read (data.data (), size)) {
    GST_ERROR_OBJECT (filter, "failed to read engine file: %s", path);
    return false;
  }
  return true;
}

void
cleanup_trt (Gstlliefilter *filter)
{
  if (filter->input_device) {
    cudaFree (filter->input_device);
    filter->input_device = nullptr;
  }
  if (filter->output_device) {
    cudaFree (filter->output_device);
    filter->output_device = nullptr;
  }
  if (filter->context) {
    delete filter->context;
    filter->context = nullptr;
  }
  if (filter->engine) {
    delete filter->engine;
    filter->engine = nullptr;
  }
  if (filter->runtime) {
    delete filter->runtime;
    filter->runtime = nullptr;
  }
  if (filter->cuda_stream) {
    cudaStreamDestroy (filter->cuda_stream);
    filter->cuda_stream = nullptr;
  }
}

} // namespace

extern "C" cudaError_t launch_preprocess_float (uint8_t *src, float *dst,
    int src_width, int src_height, int dst_height, int dst_width,
    cudaStream_t stream);

extern "C" cudaError_t launch_postprocess_float (float *src, uint8_t *dst,
    int src_height, int src_width, int dst_width, int dst_height,
    cudaStream_t stream);

static void gst_lliefilter_set_property (GObject *object, guint prop_id,
                                         const GValue *value, GParamSpec *pspec);
static void gst_lliefilter_get_property (GObject *object, guint prop_id,
                                         GValue *value, GParamSpec *pspec);

static gboolean gst_lliefilter_set_caps (GstBaseTransform *btrans,
                                         GstCaps *incaps, GstCaps *outcaps);
static gboolean gst_lliefilter_start (GstBaseTransform *btrans);
static gboolean gst_lliefilter_stop (GstBaseTransform *btrans);
static GstFlowReturn gst_lliefilter_transform_ip (GstBaseTransform *btrans,
                                                  GstBuffer *inbuf);

static void
gst_lliefilter_class_init (GstlliefilterClass *klass)
{
  GObjectClass *gobject_class = G_OBJECT_CLASS (klass);
  GstElementClass *gstelement_class = GST_ELEMENT_CLASS (klass);
  GstBaseTransformClass *basetransform_class = GST_BASE_TRANSFORM_CLASS (klass);

  gobject_class->set_property = gst_lliefilter_set_property;
  gobject_class->get_property = gst_lliefilter_get_property;

  basetransform_class->set_caps = gst_lliefilter_set_caps;
  basetransform_class->start = gst_lliefilter_start;
  basetransform_class->stop = gst_lliefilter_stop;
  basetransform_class->transform_ip = gst_lliefilter_transform_ip;

  gst_element_class_set_static_metadata (gstelement_class,
      "TensorRT Bitmap Filter", "Filter/Effect/Video",
      "In-place TensorRT image filter for DeepStream",
      "TeamGRIT");

  gst_element_class_add_pad_template (gstelement_class,
      gst_static_pad_template_get (&gst_lliefilter_sink_template));
  gst_element_class_add_pad_template (gstelement_class,
      gst_static_pad_template_get (&gst_lliefilter_src_template));

  g_object_class_install_property (gobject_class, PROP_ENGINE_PATH,
      g_param_spec_string ("engine-path", "Engine path",
          "Path to TensorRT engine file", NULL,
          (GParamFlags) (G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS)));

  g_object_class_install_property (gobject_class, PROP_GPU_ID,
      g_param_spec_uint ("gpu-id", "GPU device ID",
          "CUDA device to run inference on", 0, G_MAXUINT, 0,
          (GParamFlags) (G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS)));

  /* Set sink and src pad capabilities */
  gst_element_class_add_pad_template (gstelement_class,
      gst_static_pad_template_get (&gst_lliefilter_src_template));
  gst_element_class_add_pad_template (gstelement_class,
      gst_static_pad_template_get (&gst_lliefilter_sink_template));
}

static void
gst_lliefilter_init (Gstlliefilter *filter)
{
  GstBaseTransform *btrans = GST_BASE_TRANSFORM (filter);

  /* Use DeepStream new buffer API at runtime */
  g_setenv ("DS_NEW_BUFAPI", "1", TRUE);

  gst_base_transform_set_in_place (btrans, TRUE);
  gst_base_transform_set_passthrough (btrans, FALSE);

  filter->gpu_id = 0;
  filter->engine_path = NULL;
  filter->cuda_stream = nullptr;
  filter->runtime = nullptr;
  filter->engine = nullptr;
  filter->context = nullptr;
  filter->input_device = nullptr;
  filter->output_device = nullptr;
  filter->input_size_bytes = 0;
  filter->output_size_bytes = 0;
  filter->frame_width = 0;
  filter->frame_height = 0;

  filter->input_tensor_name[0] = '\0';
  filter->output_tensor_name[0] = '\0';
}

static void
gst_lliefilter_set_property (GObject *object, guint prop_id,
                             const GValue *value, GParamSpec *pspec)
{
  Gstlliefilter *filter = GST_LLIEFILTER (object);

  switch (prop_id) {
    case PROP_ENGINE_PATH:
      g_free (filter->engine_path);
      filter->engine_path = g_value_dup_string (value);
      break;
    case PROP_GPU_ID:
      filter->gpu_id = g_value_get_uint (value);
      break;
    default:
      G_OBJECT_WARN_INVALID_PROPERTY_ID (object, prop_id, pspec);
      break;
  }
}

static void
gst_lliefilter_get_property (GObject *object, guint prop_id,
                             GValue *value, GParamSpec *pspec)
{
  Gstlliefilter *filter = GST_LLIEFILTER (object);

  switch (prop_id) {
    case PROP_ENGINE_PATH:
      g_value_set_string (value, filter->engine_path);
      break;
    case PROP_GPU_ID:
      g_value_set_uint (value, filter->gpu_id);
      break;
    default:
      G_OBJECT_WARN_INVALID_PROPERTY_ID (object, prop_id, pspec);
      break;
  }
}

static gboolean
gst_lliefilter_set_caps (GstBaseTransform *btrans, GstCaps *incaps,
                         GstCaps *outcaps)
{
  Gstlliefilter *filter = GST_LLIEFILTER (btrans);

  if (!gst_video_info_from_caps (&filter->video_info, incaps)) {
    GST_ERROR_OBJECT (filter, "failed to parse input caps");
    return FALSE;
  }

  filter->frame_width = GST_VIDEO_INFO_WIDTH (&filter->video_info);
  filter->frame_height = GST_VIDEO_INFO_HEIGHT (&filter->video_info);

  return TRUE;
}

static gboolean
gst_lliefilter_start (GstBaseTransform *btrans)
{
  Gstlliefilter *filter = GST_LLIEFILTER (btrans);

  if (filter->engine_path == NULL || filter->engine_path[0] == '\0') {
    GST_ERROR_OBJECT (filter, "engine-path is required");
    return FALSE;
  }

  if (cudaSetDevice (filter->gpu_id) != cudaSuccess) {
    GST_ERROR_OBJECT (filter, "failed to set CUDA device %u", filter->gpu_id);
    return FALSE;
  }

  if (cudaStreamCreate (&filter->cuda_stream) != cudaSuccess) {
    GST_ERROR_OBJECT (filter, "failed to create CUDA stream");
    return FALSE;
  }

  std::vector<char> engine_data;
  if (!load_engine (filter->engine_path, engine_data, filter)) {
    cleanup_trt (filter);
    return FALSE;
  }

  filter->runtime = nvinfer1::createInferRuntime (g_trt_logger);
  if (filter->runtime == nullptr) {
    GST_ERROR_OBJECT (filter, "failed to create TensorRT runtime");
    cleanup_trt (filter);
    return FALSE;
  }

  filter->engine =
      filter->runtime->deserializeCudaEngine (engine_data.data (),
      engine_data.size ());
  if (filter->engine == nullptr) {
    GST_ERROR_OBJECT (filter, "failed to deserialize TensorRT engine");
    cleanup_trt (filter);
    return FALSE;
  }

  filter->context = filter->engine->createExecutionContext ();
  if (filter->context == nullptr) {
    GST_ERROR_OBJECT (filter, "failed to create TensorRT execution context");
    cleanup_trt (filter);
    return FALSE;
  }

  const int nb_tensors = filter->engine->getNbIOTensors ();
  int input_found = 0;
  int output_found = 0;

  for (int i = 0; i < nb_tensors; ++i) {
    const char *name = filter->engine->getIOTensorName (i);
    const auto mode = filter->engine->getTensorIOMode (name);

    if (mode == nvinfer1::TensorIOMode::kINPUT && !input_found) {
      g_strlcpy (filter->input_tensor_name, name,
          sizeof (filter->input_tensor_name));
      input_found = 1;
    } else if (mode == nvinfer1::TensorIOMode::kOUTPUT && !output_found) {
      g_strlcpy (filter->output_tensor_name, name,
          sizeof (filter->output_tensor_name));
      output_found = 1;
    }
  }

  if (!input_found || !output_found) {
    GST_ERROR_OBJECT (filter, "could not find input/output tensors");
    cleanup_trt (filter);
    return FALSE;
  }

  filter->input_dims =
      filter->engine->getTensorShape (filter->input_tensor_name);
  filter->output_dims =
      filter->engine->getTensorShape (filter->output_tensor_name);

  if (filter->input_dims.nbDims != 4 || filter->output_dims.nbDims != 4) {
    GST_ERROR_OBJECT (filter,
        "expected 4D tensors (NCHW) but got input %d dims, output %d dims",
        filter->input_dims.nbDims, filter->output_dims.nbDims);
    cleanup_trt (filter);
    return FALSE;
  }

  if (filter->input_dims.d[0] != 1 || filter->input_dims.d[1] != 3) {
    GST_ERROR_OBJECT (filter,
        "only 1x3xHxW input supported for now, got N=%ld C=%ld",
        (long) filter->input_dims.d[0], (long) filter->input_dims.d[1]);
    cleanup_trt (filter);
    return FALSE;
  }

  if (filter->output_dims.d[0] != 1 || filter->output_dims.d[1] != 3) {
    GST_ERROR_OBJECT (filter,
        "only 1x3xHxW output supported for now, got N=%ld C=%ld",
        (long) filter->output_dims.d[0], (long) filter->output_dims.d[1]);
    cleanup_trt (filter);
    return FALSE;
  }

  const nvinfer1::DataType input_dtype =
      filter->engine->getTensorDataType (filter->input_tensor_name);
  const nvinfer1::DataType output_dtype =
      filter->engine->getTensorDataType (filter->output_tensor_name);

  if (input_dtype != nvinfer1::DataType::kFLOAT ||
      output_dtype != nvinfer1::DataType::kFLOAT) {
    GST_ERROR_OBJECT (filter,
        "only FP32<->FP32 tensors supported for now (got input %d, output %d)",
        static_cast<int> (input_dtype), static_cast<int> (output_dtype));
    cleanup_trt (filter);
    return FALSE;
  }

  filter->input_size_bytes =
      dims_volume (filter->input_dims) * sizeof (float);
  filter->output_size_bytes =
      dims_volume (filter->output_dims) * sizeof (float);

  if (cudaMalloc (&filter->input_device, filter->input_size_bytes) !=
      cudaSuccess) {
    GST_ERROR_OBJECT (filter, "failed to allocate input buffer");
    cleanup_trt (filter);
    return FALSE;
  }

  if (cudaMalloc (&filter->output_device, filter->output_size_bytes) !=
      cudaSuccess) {
    GST_ERROR_OBJECT (filter, "failed to allocate output buffer");
    cleanup_trt (filter);
    return FALSE;
  }

  if (!filter->context->setInputShape (filter->input_tensor_name,
          filter->input_dims)) {
    GST_ERROR_OBJECT (filter, "failed to set input shape");
    cleanup_trt (filter);
    return FALSE;
  }

  if (!filter->context->setTensorAddress (filter->input_tensor_name,
          filter->input_device)) {
    GST_ERROR_OBJECT (filter, "failed to bind input tensor");
    cleanup_trt (filter);
    return FALSE;
  }

  if (!filter->context->setTensorAddress (filter->output_tensor_name,
          filter->output_device)) {
    GST_ERROR_OBJECT (filter, "failed to bind output tensor");
    cleanup_trt (filter);
    return FALSE;
  }

  return TRUE;
}

static gboolean
gst_lliefilter_stop (GstBaseTransform *btrans)
{
  Gstlliefilter *filter = GST_LLIEFILTER (btrans);

  cleanup_trt (filter);
  g_clear_pointer (&filter->engine_path, g_free);

  return TRUE;
}

static GstFlowReturn
gst_lliefilter_transform_ip (GstBaseTransform *btrans, GstBuffer *inbuf)
{
  Gstlliefilter *filter = GST_LLIEFILTER (btrans);

  GstMapInfo in_map_info;
  if (!gst_buffer_map (inbuf, &in_map_info, GST_MAP_READWRITE)) {
    GST_ERROR_OBJECT (filter, "failed to map input buffer");
    return GST_FLOW_ERROR;
  }

  NvBufSurface *surface = (NvBufSurface *) in_map_info.data;
  if (surface == nullptr) {
    GST_ERROR_OBJECT (filter, "failed to get NvBufSurface from buffer data");
    gst_buffer_unmap (inbuf, &in_map_info);
    return GST_FLOW_ERROR;
  }

  if (surface->gpuId != static_cast<int> (filter->gpu_id)) {
    GST_ERROR_OBJECT (filter,
        "input surface gpu-id (%d) does not match configured gpu-id (%u)",
        surface->gpuId, filter->gpu_id);
    return GST_FLOW_ERROR;
  }

  for (guint i = 0; i < surface->batchSize; ++i) {
    NvBufSurfaceParams *params = &surface->surfaceList[i];

    /* Ensure latest contents are visible to device before launching kernels. */
    NvBufSurfaceSyncForDevice (surface, i, 0);

    cudaError_t pre_err =
        launch_preprocess_float ((uint8_t *) params->dataPtr,
        (float *) filter->input_device, params->width, params->height,
        filter->input_dims.d[2], filter->input_dims.d[3],
        filter->cuda_stream);

    if (pre_err != cudaSuccess) {
      GST_ERROR_OBJECT (filter, "preprocess kernel failed: %s",
          cudaGetErrorName (pre_err));
      gst_buffer_unmap (inbuf, &in_map_info);
      return GST_FLOW_ERROR;
    }

    if (!filter->context->enqueueV3 (filter->cuda_stream)) {
      GST_ERROR_OBJECT (filter, "TensorRT enqueueV3 failed");
      gst_buffer_unmap (inbuf, &in_map_info);
      return GST_FLOW_ERROR;
    }

    cudaError_t post_err =
        launch_postprocess_float ((float *) filter->output_device,
        (uint8_t *) params->dataPtr, filter->output_dims.d[2],
        filter->output_dims.d[3], params->width, params->height,
        filter->cuda_stream);
    if (post_err != cudaSuccess) {
      GST_ERROR_OBJECT (filter, "postprocess kernel failed: %s",
          cudaGetErrorName (post_err));
      gst_buffer_unmap (inbuf, &in_map_info);
      return GST_FLOW_ERROR;
    }

    if (cudaStreamSynchronize (filter->cuda_stream) != cudaSuccess) {
      GST_ERROR_OBJECT (filter, "cudaStreamSynchronize failed");
      gst_buffer_unmap (inbuf, &in_map_info);
      return GST_FLOW_ERROR;
    }
    NvBufSurfaceSyncForDevice (surface, i, 0);
  }

  gst_buffer_unmap (inbuf, &in_map_info);
  return GST_FLOW_OK;
}

static gboolean
plugin_init (GstPlugin *plugin)
{
  GST_DEBUG_CATEGORY_INIT (gst_lliefilter_debug, "lliefilter", 0,
      "TensorRT image filter");

  return gst_element_register (plugin, "lliefilter", GST_RANK_NONE,
      GST_TYPE_LLIEFILTER);
}

GST_PLUGIN_DEFINE (GST_VERSION_MAJOR,
    GST_VERSION_MINOR,
    nvdsgst_lliefilter,
    DESCRIPTION, plugin_init, VERSION, LICENSE, BINARY_PACKAGE, URL)
