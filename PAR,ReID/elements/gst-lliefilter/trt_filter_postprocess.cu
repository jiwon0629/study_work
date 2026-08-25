#include <cuda_runtime.h>
#include <stdint.h>

// RGB, NCHW FP32 -> RGBA postprocessing.
// Assumptions:
// - Input TensorRT tensor is 1x3xH xW float (NCHW) with values in [0, 1].
// - Output NvBufSurface is tightly packed RGBA 8-bit.

static __global__ void
postprocess_nchw_float_to_rgba (const float *src, uint8_t *dst,
    int src_height, int src_width, int dst_width, int dst_height)
{
  int x = blockIdx.x * blockDim.x + threadIdx.x;
  int y = blockIdx.y * blockDim.y + threadIdx.y;

  if (x >= dst_width || y >= dst_height || x >= src_width || y >= src_height) {
    return;
  }

  int plane_size = src_width * src_height;
  int idx = y * src_width + x;

  float r = src[idx];
  float g = src[plane_size + idx];
  float b = src[2 * plane_size + idx];

  r = fminf (fmaxf (r, 0.0f), 1.0f);
  g = fminf (fmaxf (g, 0.0f), 1.0f);
  b = fminf (fmaxf (b, 0.0f), 1.0f);

  int dst_idx = (y * dst_width + x) * 4;
  dst[dst_idx + 0] = static_cast<uint8_t> (r * 255.0f);
  dst[dst_idx + 1] = static_cast<uint8_t> (g * 255.0f);
  dst[dst_idx + 2] = static_cast<uint8_t> (b * 255.0f);
  dst[dst_idx + 3] = 255;
}

extern "C" cudaError_t
launch_postprocess_float (float *src, uint8_t *dst, int src_height,
    int src_width, int dst_width, int dst_height, cudaStream_t stream)
{
  dim3 block (16, 16);
  dim3 grid ((dst_width + block.x - 1) / block.x,
      (dst_height + block.y - 1) / block.y);

  postprocess_nchw_float_to_rgba<<<grid, block, 0, stream>>>(
      src, dst, src_height, src_width, dst_width, dst_height);

  return cudaGetLastError ();
}
