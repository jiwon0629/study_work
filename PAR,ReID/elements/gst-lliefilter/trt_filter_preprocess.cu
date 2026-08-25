#include <cuda_runtime.h>
#include <stdint.h>

// RGBA -> RGB, NCHW preprocessing for FP32 TensorRT input.
// Assumptions:
// - Input NvBufSurface is tightly packed RGBA (4 bytes per pixel).
// - Output TensorRT tensor is 1x3xH xW (NCHW) with float values in [0, 1].

static __global__ void
preprocess_rgba_to_nchw_float (const uint8_t *src, float *dst,
    int src_width, int src_height, int dst_width, int dst_height)
{
  int x = blockIdx.x * blockDim.x + threadIdx.x;
  int y = blockIdx.y * blockDim.y + threadIdx.y;

  if (x >= dst_width || y >= dst_height || x >= src_width || y >= src_height) {
    return;
  }

  int src_idx = (y * src_width + x) * 4;
  uint8_t r = src[src_idx + 0];
  uint8_t g = src[src_idx + 1];
  uint8_t b = src[src_idx + 2];

  int plane_size = dst_width * dst_height;
  int idx = y * dst_width + x;

  const float scale = 1.0f / 255.0f;
  dst[idx] = static_cast<float> (r) * scale;
  dst[plane_size + idx] = static_cast<float> (g) * scale;
  dst[2 * plane_size + idx] = static_cast<float> (b) * scale;
}

extern "C" cudaError_t
launch_preprocess_float (uint8_t *src, float *dst, int src_width,
    int src_height, int dst_height, int dst_width, cudaStream_t stream)
{
  dim3 block (16, 16);
  dim3 grid ((dst_width + block.x - 1) / block.x,
      (dst_height + block.y - 1) / block.y);

  preprocess_rgba_to_nchw_float<<<grid, block, 0, stream>>>(
      src, dst, src_width, src_height, dst_width, dst_height);

  return cudaGetLastError ();
}
