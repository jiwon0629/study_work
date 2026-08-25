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

#ifndef __GST_LLIEFILTER_H__
#define __GST_LLIEFILTER_H__

#include <gst/base/gstbasetransform.h>
#include <gst/video/video.h>

#include <cuda.h>
#include <cuda_runtime.h>
#include <NvInfer.h>

#include "nvbufsurface.h"
#include "nvbufsurftransform.h"
#include "gst-nvquery.h"
#include "gstnvdsmeta.h"

G_BEGIN_DECLS

typedef struct _Gstlliefilter Gstlliefilter;
typedef struct _GstlliefilterClass GstlliefilterClass;

#define GST_TYPE_LLIEFILTER (gst_lliefilter_get_type())
#define GST_LLIEFILTER(obj) (G_TYPE_CHECK_INSTANCE_CAST((obj), GST_TYPE_LLIEFILTER, Gstlliefilter))
#define GST_LLIEFILTER_CLASS(klass) (G_TYPE_CHECK_CLASS_CAST((klass), GST_TYPE_LLIEFILTER, GstlliefilterClass))
#define GST_LLIEFILTER_GET_CLASS(obj) (G_TYPE_INSTANCE_GET_CLASS((obj), GST_TYPE_LLIEFILTER, GstlliefilterClass))
#define GST_IS_LLIEFILTER(obj) (G_TYPE_CHECK_INSTANCE_TYPE((obj), GST_TYPE_LLIEFILTER))
#define GST_IS_LLIEFILTER_CLASS(klass) (G_TYPE_CHECK_CLASS_TYPE((klass), GST_TYPE_LLIEFILTER))
#define GST_LLIEFILTER_CAST(obj) ((Gstlliefilter *)(obj))

/* Package and library details required for plugin_init */
#define PACKAGE "lliefilter"
#define VERSION "1.0"
#define LICENSE "Proprietary"
#define DESCRIPTION "TensorRT bitmap filter for DeepStream 8.0"
#define BINARY_PACKAGE "TeamGRIT DeepStream lliefilter plugin"
#define URL "http://nvidia.com/"

struct _Gstlliefilter {
  GstBaseTransform parent;

  guint gpu_id;
  gchar *engine_path;

  cudaStream_t cuda_stream;
  nvinfer1::IRuntime *runtime;
  nvinfer1::ICudaEngine *engine;
  nvinfer1::IExecutionContext *context;

  nvinfer1::Dims input_dims;
  nvinfer1::Dims output_dims;

  char input_tensor_name[128];
  char output_tensor_name[128];

  void *input_device;
  void *output_device;

  size_t input_size_bytes;
  size_t output_size_bytes;

  guint frame_width;
  guint frame_height;

  GstVideoInfo video_info;
};

struct _GstlliefilterClass {
  GstBaseTransformClass parent_class;
};

GType gst_lliefilter_get_type(void);

G_END_DECLS

#endif /* __GST_LLIEFILTER_H__ */
