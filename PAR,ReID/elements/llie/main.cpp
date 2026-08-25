#include <iostream>
#include <string>

#include "error.h"
#include "gst_runner.h"
#include "moth_config_overrides.h"
#include "strict_config.h"

namespace {

struct AppConfig {
    std::string input_url;
    int latency_ms = 200;
    bool use_tcp = true;
    std::string name;
    std::string moth_config_path = "/opt/mantis/runtime/config_tcp.txt";
    int gpu_id = 0;
};

AppConfig load_config_or_throw(const std::string& config_path) {
#ifdef NO_JSON_SUPPORT
    (void)config_path;
    mantis::fail("CONFIG_SCHEMA", "JSON support is required");
#else
    const auto j = mantis::load_json_file_or_throw(config_path, "llie config");
    const auto schema = mantis::load_json_file_or_throw("/opt/mantis/runtime/schemas/elements/llie.schema.json", "llie schema");
    mantis::validate_json_against_schema_or_throw(j, schema, "root");

    AppConfig cfg;
    if (!j.contains("input_url")) {
        mantis::fail("CONFIG_SCHEMA", "input_url is required");
    }
    cfg.input_url = j.at("input_url").get<std::string>();
    if (j.contains("latency_ms")) cfg.latency_ms = j.at("latency_ms").get<int>();
    if (j.contains("use_tcp")) cfg.use_tcp = j.at("use_tcp").get<bool>();
    if (j.contains("name")) cfg.name = j.at("name").get<std::string>();
    if (j.contains("moth_config_path")) cfg.moth_config_path = j.at("moth_config_path").get<std::string>();
    if (j.contains("gpu_id")) cfg.gpu_id = j.at("gpu_id").get<int>();
    return cfg;
#endif
}

std::string build_pipeline(const AppConfig& cfg, const std::string& moth_cfg) {
    constexpr int kTargetWidth = 1920;
    constexpr int kTargetHeight = 1080;
    const std::string engine_path =
        "/opt/mantis/runtime/model_repository/llie/NOX_trt109_1080p_int8_b1.engine";

    const std::string protocol = cfg.use_tcp ? "tcp" : "udp";
    return "rtspsrc location=" + cfg.input_url +
        " protocols=" + protocol +
        " latency=" + std::to_string(cfg.latency_ms) +
        " drop-on-latency=false ! "
        "rtph264depay ! "
        "h264parse config-interval=-1 disable-passthrough=true ! "
        "video/x-h264,alignment=au ! "
        "nvv4l2decoder gpu-id=" + std::to_string(cfg.gpu_id) +
        " ! videorate ! video/x-raw(memory:NVMM),framerate=30/1 ! "
        "queue name=queue-post-decode max-size-buffers=1 leaky=2 ! "
        "nvvideoconvert gpu-id=" + std::to_string(cfg.gpu_id) +
        " nvbuf-memory-type=0 ! "
        "video/x-raw(memory:NVMM),format=RGBA,width=" + std::to_string(kTargetWidth) +
        ",height=" + std::to_string(kTargetHeight) + " ! "
        "lliefilter engine-path=" + engine_path + " gpu-id=" + std::to_string(cfg.gpu_id) + " ! "
        "nvvideoconvert gpu-id=" + std::to_string(cfg.gpu_id) +
        " nvbuf-memory-type=0 ! "
        "video/x-raw(memory:NVMM),format=NV12,width=" + std::to_string(kTargetWidth) +
        ",height=" + std::to_string(kTargetHeight) + " ! "
        "queue name=queue-enc max-size-buffers=1 leaky=0 ! "
        "nvv4l2h264enc name=encoder insert-sps-pps=true bitrate=2000000 gpu-id=" + std::to_string(cfg.gpu_id) + " ! "
        "h264parse name=parser-enc config-interval=1 ! "
        "mothtcpsink config-path=" + moth_cfg;
}

} // namespace

int main(int argc, char** argv) {
    try {
        const auto cli = mantis::parse_cli_or_throw(argc, argv);
        const auto cfg = load_config_or_throw(cli.config_file);

        if (cli.validate_only) {
            std::cout << "config validation passed" << std::endl;
            return 0;
        }

        const auto moth_cfg = mantis::write_moth_config_override_or_throw(cfg.moth_config_path, cfg.name, "llie");
        const auto pipeline = build_pipeline(cfg, moth_cfg);
        g_setenv("GST_DEBUG", "mothtcpsink:6", TRUE);
        return mantis::run_pipeline_or_throw(&argc, &argv, pipeline);
    } catch (const std::exception& e) {
        std::cerr << e.what() << std::endl;
        return 1;
    }
}
