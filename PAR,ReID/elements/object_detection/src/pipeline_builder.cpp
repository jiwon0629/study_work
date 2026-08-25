#include "pipeline_builder.h"

#include <sstream>

namespace mantis::elements::object_detection {

std::string build_pipeline_description(const PipelineOptions& opts) {
    const std::string protocol = opts.use_tcp ? "tcp" : "udp";
    std::ostringstream desc;

    desc << "rtspsrc location=" << opts.input_url
         << " protocols=" << protocol
         << " latency=" << opts.latency_ms
         << " drop-on-latency=false ! "
         << "rtph264depay ! "
         << "h264parse config-interval=-1 disable-passthrough=true ! "
         << "video/x-h264,alignment=au ! ";

    if (opts.variant == PipelineVariant::kLlieObjectDetection) {
        constexpr int kTargetWidth = 1920;
        constexpr int kTargetHeight = 1080;
        const std::string engine_path =
            "/opt/mantis/runtime/model_repository/llie/NOX_trt109_1080p_int8_b1.engine";

        desc << "queue name=queue-pre-decode ! "
             << "nvv4l2decoder gpu-id=" << opts.gpu_id << " ! "
             << "videorate ! video/x-raw(memory:NVMM),framerate=30/1 ! "
             << "queue name=queue-post-decode max-size-buffers=1 leaky=2 ! "
             << "nvvideoconvert gpu-id=" << opts.gpu_id
             << " nvbuf-memory-type=" << opts.nvbuf_memory_type << " ! "
             << "video/x-raw(memory:NVMM),format=RGBA,width=" << kTargetWidth
             << ",height=" << kTargetHeight << " ! "
             << "lliefilter engine-path=" << engine_path << " gpu-id=" << opts.gpu_id << " ! "
             << "nvvideoconvert gpu-id=" << opts.gpu_id
             << " nvbuf-memory-type=" << opts.nvbuf_memory_type << " ! "
             << "video/x-raw(memory:NVMM),format=NV12,width=" << kTargetWidth
             << ",height=" << kTargetHeight << " ! ";
    } else {
        desc << "nvv4l2decoder gpu-id=" << opts.gpu_id << " ! "
             << "queue name=queue-post-decode max-size-buffers=1 leaky=2 ! ";
    }

    desc << "streammux.sink_0 "
         << "nvstreammux name=streammux "
         << "batch-size=" << opts.batch_size << " "
         << "width=" << opts.streammux_width << " "
         << "height=" << opts.streammux_height << " "
         << "live-source=" << (opts.variant == PipelineVariant::kLlieObjectDetection ? "true" : "false") << " "
         << "batched-push-timeout=40000 "
         << "gpu-id=" << opts.gpu_id << " "
         << "nvbuf-memory-type=" << opts.nvbuf_memory_type << " ! "
         << "nvinfer name=primary-infer "
         << "config-file-path=" << opts.infer_config_path << " "
         << "batch-size=" << opts.batch_size << " "
         << "gpu-id=" << opts.gpu_id << " ! "
         << "nvtracker name=tracker "
         << "ll-lib-file=" << opts.tracker_lib_path << " "
         << "ll-config-file=" << opts.tracker_config_path << " "
         << "gpu-id=" << opts.gpu_id << " "
         << "tracker-width=640 "
         << "tracker-height=384 "
         << "display-tracking-id=1 ! "
         << "nvvideoconvert name=nvvidconv-pre-osd "
         << "gpu-id=" << opts.gpu_id << " "
         << "nvbuf-memory-type=" << opts.nvbuf_memory_type << " ! "
         << "video/x-raw(memory:NVMM),format=RGBA ! "
         << "nvdsosd name=osd gpu-id=" << opts.gpu_id << " ! "
         << "nvvideoconvert name=nvvidconv-post "
         << "gpu-id=" << opts.gpu_id << " "
         << "nvbuf-memory-type=" << opts.nvbuf_memory_type << " ! "
         << "video/x-raw(memory:NVMM),format=NV12 ! "
         << "queue name=queue-enc max-size-buffers=1 leaky=0 ! "
         << "nvv4l2h264enc name=encoder insert-sps-pps=true bitrate=" << opts.video_bitrate
         << " gpu-id=" << opts.gpu_id << " ! "
         << "h264parse name=parser-enc config-interval=1 ! "
         << "mothtcpsink name=moth-sink config-path=" << opts.moth_config_path;

    return desc.str();
}

} // namespace mantis::elements::object_detection
