#pragma once

#include <string>

namespace mantis::elements::object_detection {

enum class PipelineVariant {
    kObjectDetection,
    kLlieObjectDetection,
};

struct PipelineOptions {
    PipelineVariant variant = PipelineVariant::kObjectDetection;
    std::string input_url;
    int latency_ms = 200;
    bool use_tcp = true;
    int batch_size = 1;
    int streammux_width = 1920;
    int streammux_height = 1080;
    int gpu_id = 0;
    int nvbuf_memory_type = 0;
    std::string infer_config_path;
    std::string tracker_lib_path;
    std::string tracker_config_path;
    int video_bitrate = 2000000;
    std::string moth_config_path;
};

std::string build_pipeline_description(const PipelineOptions& opts);

} // namespace mantis::elements::object_detection
