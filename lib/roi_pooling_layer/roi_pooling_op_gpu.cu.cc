#if GOOGLE_CUDA

#define EIGEN_USE_GPU

#include <stdio.h>
#include <cfloat>
#include "roi_pooling_op_gpu.h"

#define CUDA_1D_KERNEL_LOOP(i, n)                            \
  for (int i = blockIdx.x * blockDim.x + threadIdx.x; i < n; \
       i += blockDim.x * gridDim.x)

using std::max;
using std::min;

// namespace tensorflow {
using namespace tensorflow;

template <typename Dtype>
__global__ void ROIPoolForward(const int nthreads, const Dtype* bottom_data,
    const Dtype spatial_scale, const int pool_channel, const int height, const int width,
    const int channels, const int pooled_height, const int pooled_width, const int channel_rois,
    const Dtype* bottom_rois, Dtype* top_data, int* argmax_data)
{
  CUDA_1D_KERNEL_LOOP(index, nthreads)
  {
    // (n, ph, pw, c) is an element in the pooled output
    int n = index;

    int c;
    if (pool_channel)
      c = 1;
    else
    {
      c = n % channels;
      n /= channels;
    }

    int pw = n % pooled_width;
    n /= pooled_width;

    int ph = n % pooled_height;
    n /= pooled_height;

    const Dtype* offset_bottom_rois = bottom_rois + n * channel_rois;
    int roi_batch_ind = int(offset_bottom_rois[0]);
    int roi_cls = int(offset_bottom_rois[1]);
    int roi_start_w = round(offset_bottom_rois[2] * spatial_scale);
    int roi_start_h = round(offset_bottom_rois[3] * spatial_scale);
    int roi_end_w = round(offset_bottom_rois[4] * spatial_scale);
    int roi_end_h = round(offset_bottom_rois[5] * spatial_scale);

    // Force malformed ROIs to be 1x1
    int roi_width = max(roi_end_w - roi_start_w + 1, 1);
    int roi_height = max(roi_end_h - roi_start_h + 1, 1);
    Dtype bin_size_h = static_cast<Dtype>(roi_height)
                       / static_cast<Dtype>(pooled_height);
    Dtype bin_size_w = static_cast<Dtype>(roi_width)
                       / static_cast<Dtype>(pooled_width);

    int hstart = static_cast<int>(floor(static_cast<Dtype>(ph)
                                        * bin_size_h));
    int wstart = static_cast<int>(floor(static_cast<Dtype>(pw)
                                        * bin_size_w));
    int hend = static_cast<int>(ceil(static_cast<Dtype>(ph + 1)
                                     * bin_size_h));
    int wend = static_cast<int>(ceil(static_cast<Dtype>(pw + 1)
                                     * bin_size_w));

    // Add roi offsets and clip to input boundaries
    hstart = min(max(hstart + roi_start_h, 0), height);
    hend = min(max(hend + roi_start_h, 0), height);
    wstart = min(max(wstart + roi_start_w, 0), width);
    wend = min(max(wend + roi_start_w, 0), width);
    bool is_empty = (hend <= hstart) || (wend <= wstart);

    // Define an empty pooling region to be zero
    Dtype maxval = is_empty ? 0 : -FLT_MAX;
    // If nothing is pooled, argmax = -1 causes nothing to be backprop'd
    int maxidx = -1;
    bottom_data += roi_batch_ind * channels * height * width;
    for (int h = hstart; h < hend; ++h)
    {
      for (int w = wstart; w < wend; ++w)
      {
        int bottom_index;
        if (pool_channel)
          bottom_index = (h * width + w) * channels + roi_cls;
        else
          bottom_index = (h * width + w) * channels + c;
        if (bottom_data[bottom_index] > maxval) {
          maxval = bottom_data[bottom_index];
          maxidx = bottom_index;
        }
      }
    }
    top_data[index] = maxval;
    if (argmax_data != nullptr)
      argmax_data[index] = maxidx;
  }
}

bool ROIPoolForwardLaucher(
    const float* bottom_data, const float spatial_scale, const int pool_channel, const int num_rois, const int channel_rois, const int height,
    const int width, const int channels, const int pooled_height,
    const int pooled_width, const float* bottom_rois,
    float* top_data, int* argmax_data, const Eigen::GpuDevice& d)
{
  const int kThreadsPerBlock = 512;
  int output_size;
  cudaError_t err;

  if (pool_channel)
    output_size = num_rois * pooled_height * pooled_width;
  else
    output_size = num_rois * pooled_height * pooled_width * channels;

  ROIPoolForward<<<(output_size + kThreadsPerBlock - 1) / kThreadsPerBlock,
                       kThreadsPerBlock, 0, d.stream()>>>(
      output_size, bottom_data, spatial_scale, pool_channel, height, width, channels, pooled_height,
      pooled_width, channel_rois, bottom_rois, top_data, argmax_data);

  err = cudaGetLastError();
  if(cudaSuccess != err)
  {
    fprintf( stderr, "cudaCheckError() failed : %s\n", cudaGetErrorString( err ) );
    exit( -1 );
  }

  return d.ok();
}


template <typename Dtype>
__global__ void ROIPoolBackward(const int nthreads, const Dtype* top_diff,
    const int* argmax_data, const int num_rois, const int channel_rois, const Dtype spatial_scale, const int pool_channel,
    const int height, const int width, const int channels,
    const int pooled_height, const int pooled_width, Dtype* bottom_diff,
    const Dtype* bottom_rois) {
  CUDA_1D_KERNEL_LOOP(index, nthreads)
  {
    // (n, h, w, c) coords in bottom data
    int n = index;
    int c = n % channels;
    n /= channels;
    int w = n % width;
    n /= width;
    int h = n % height;
    n /= height;

    Dtype gradient = 0;
    // Accumulate gradient over all ROIs that pooled this element
    for (int roi_n = 0; roi_n < num_rois; ++roi_n)
    {
      const Dtype* offset_bottom_rois = bottom_rois + roi_n * channel_rois;
      int roi_batch_ind = int(offset_bottom_rois[0]);
      int roi_cls = int(offset_bottom_rois[1]);
      // Skip if ROI's batch index doesn't match n
      if (n != roi_batch_ind)
        continue;

      if (pool_channel)
      {
        if (c != roi_cls)
          continue;
      }

      int roi_start_w = round(offset_bottom_rois[2] * spatial_scale);
      int roi_start_h = round(offset_bottom_rois[3] * spatial_scale);
      int roi_end_w = round(offset_bottom_rois[4] * spatial_scale);
      int roi_end_h = round(offset_bottom_rois[5] * spatial_scale);

      // Skip if ROI doesn't include (h, w)
      const bool in_roi = (w >= roi_start_w && w <= roi_end_w &&
                           h >= roi_start_h && h <= roi_end_h);
      if (!in_roi) {
        continue;
      }

      int offset;
      if (pool_channel)
        offset = roi_n * pooled_height * pooled_width;
      else
        offset = roi_n * pooled_height * pooled_width * channels;
      const Dtype* offset_top_diff = top_diff + offset;
      const int* offset_argmax_data = argmax_data + offset;

      // Compute feasible set of pooled units that could have pooled
      // this bottom unit

      // Force malformed ROIs to be 1x1
      int roi_width = max(roi_end_w - roi_start_w + 1, 1);
      int roi_height = max(roi_end_h - roi_start_h + 1, 1);

      Dtype bin_size_h = static_cast<Dtype>(roi_height)
                         / static_cast<Dtype>(pooled_height);
      Dtype bin_size_w = static_cast<Dtype>(roi_width)
                         / static_cast<Dtype>(pooled_width);

      int phstart = floor(static_cast<Dtype>(h - roi_start_h) / bin_size_h);
      int phend = ceil(static_cast<Dtype>(h - roi_start_h + 1) / bin_size_h);
      int pwstart = floor(static_cast<Dtype>(w - roi_start_w) / bin_size_w);
      int pwend = ceil(static_cast<Dtype>(w - roi_start_w + 1) / bin_size_w);

      phstart = min(max(phstart, 0), pooled_height);
      phend = min(max(phend, 0), pooled_height);
      pwstart = min(max(pwstart, 0), pooled_width);
      pwend = min(max(pwend, 0), pooled_width);

      for (int ph = phstart; ph < phend; ++ph)
      {
        for (int pw = pwstart; pw < pwend; ++pw)
        {
          if (pool_channel)
          {
            if (offset_argmax_data[ph * pooled_width + pw] == (h * width + w) * channels + c)
              gradient += offset_top_diff[ph * pooled_width + pw];
          }
          else
          {
            if (offset_argmax_data[(ph * pooled_width + pw) * channels + c] == (h * width + w) * channels + c)
              gradient += offset_top_diff[(ph * pooled_width + pw) * channels + c];
          }
        }
      }
    }
    bottom_diff[index] = gradient;
  }
}


bool ROIPoolBackwardLaucher(const float* top_diff, const float spatial_scale, const int pool_channel, const int batch_size, const int num_rois,
    const int channel_rois, const int height, const int width, const int channels, const int pooled_height,
    const int pooled_width, const float* bottom_rois,
    float* bottom_diff, const int* argmax_data, const Eigen::GpuDevice& d)
{
  const int kThreadsPerBlock = 512;
  const int output_size = batch_size * height * width * channels;
  cudaError_t err;

  ROIPoolBackward<<<(output_size + kThreadsPerBlock - 1) / kThreadsPerBlock,
                       kThreadsPerBlock, 0, d.stream()>>>(
      output_size, top_diff, argmax_data, num_rois, channel_rois, spatial_scale, pool_channel, height, width, channels, pooled_height,
      pooled_width, bottom_diff, bottom_rois);

  err = cudaGetLastError();
  if(cudaSuccess != err)
  {
    fprintf( stderr, "cudaCheckError() failed : %s\n", cudaGetErrorString( err ) );
    exit( -1 );
  }

  return d.ok();
}

// }  // namespace tensorflow

#endif  // GOOGLE_CUDA
