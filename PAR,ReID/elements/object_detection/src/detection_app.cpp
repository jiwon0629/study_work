#include "detection_app.h"

#include <filesystem>
#include <iostream>
#include <set>
#include <vector>

#include "error.h"
#include "gst_runner.h"
#include "label_filter.h"
#include "moth_config_overrides.h"
#include "strict_config.h"

namespace mantis::elements::object_detection {

namespace {

struct AppConfig {
    std::string input_url;
    std::string infer_config_path = "/opt/mantis/runtime/elements/object_detection/configs/primary_infer_config.txt";
    std::string moth_config_path = "/opt/mantis/runtime/config_tcp.txt";
    std::string tracker_config_path = "/opt/mantis/runtime/elements/object_detection/configs/primary_tracker_config.txt";
    std::string tracker_lib_path = "/opt/nvidia/deepstream/deepstream/lib/libnvds_nvmultiobjecttracker.so";
    std::string name;
    int latency_ms = 200;
    bool use_tcp = true;
    int batch_size = 1;
    int streammux_width = 1920;
    int streammux_height = 1080;
    int gpu_id = 0;
    int nvbuf_memory_type = 0;
    double confidence_threshold = 0.5;
    std::vector<std::string> labels;
    std::string label_file = "/opt/mantis/runtime/model_repository/rtdetr_trt/labels.txt";
    std::string object_detection_weight;
    int video_bitrate = 2000000;
};

AppConfig load_app_config_or_throw(const std::string& path, PipelineVariant variant) {
#ifdef NO_JSON_SUPPORT
    (void)path;
    (void)variant;
    mantis::fail("CONFIG_SCHEMA", "JSON support is required");
#else
    const auto cfg_json = mantis::load_json_file_or_throw(path, "element config");
    const std::string schema_path = variant == PipelineVariant::kLlieObjectDetection
        ? "/opt/mantis/runtime/schemas/elements/llie_object_detection.schema.json"
        : "/opt/mantis/runtime/schemas/elements/object_detection.schema.json";
    const auto schema_json = mantis::load_json_file_or_throw(schema_path, "element schema");
    mantis::validate_json_against_schema_or_throw(cfg_json, schema_json, "root");

    AppConfig cfg;
    if (!cfg_json.contains("input_url")) {
        mantis::fail("CONFIG_SCHEMA", "input_url is required");
    }
    cfg.input_url = cfg_json.at("input_url").get<std::string>();
    if (cfg_json.contains("infer_config_path")) cfg.infer_config_path = cfg_json.at("infer_config_path").get<std::string>();
    if (cfg_json.contains("moth_config_path")) cfg.moth_config_path = cfg_json.at("moth_config_path").get<std::string>();
    if (cfg_json.contains("tracker_config_path")) cfg.tracker_config_path = cfg_json.at("tracker_config_path").get<std::string>();
    if (cfg_json.contains("tracker_lib_path")) cfg.tracker_lib_path = cfg_json.at("tracker_lib_path").get<std::string>();
    if (cfg_json.contains("name")) cfg.name = cfg_json.at("name").get<std::string>();
    if (cfg_json.contains("latency_ms")) cfg.latency_ms = cfg_json.at("latency_ms").get<int>();
    if (cfg_json.contains("use_tcp")) cfg.use_tcp = cfg_json.at("use_tcp").get<bool>();
    if (cfg_json.contains("batch_size")) cfg.batch_size = cfg_json.at("batch_size").get<int>();
    if (cfg_json.contains("streammux_width")) cfg.streammux_width = cfg_json.at("streammux_width").get<int>();
    if (cfg_json.contains("streammux_height")) cfg.streammux_height = cfg_json.at("streammux_height").get<int>();
    if (cfg_json.contains("gpu_id")) cfg.gpu_id = cfg_json.at("gpu_id").get<int>();
    if (cfg_json.contains("nvbuf_memory_type")) cfg.nvbuf_memory_type = cfg_json.at("nvbuf_memory_type").get<int>();
    if (cfg_json.contains("confidence_threshold")) {
        cfg.confidence_threshold = cfg_json.at("confidence_threshold").get<double>();
    }
    if (cfg_json.contains("labels")) cfg.labels = cfg_json.at("labels").get<std::vector<std::string>>();
    if (cfg_json.contains("label_file")) cfg.label_file = cfg_json.at("label_file").get<std::string>();
    if (cfg_json.contains("object_detection_weight")) {
        cfg.object_detection_weight = cfg_json.at("object_detection_weight").get<std::string>();
    }
    if (cfg_json.contains("video_bitrate")) cfg.video_bitrate = cfg_json.at("video_bitrate").get<int>();

    if (variant == PipelineVariant::kLlieObjectDetection) {
        if (!cfg_json.contains("streammux_width")) cfg.streammux_width = 1280;
        if (!cfg_json.contains("streammux_height")) cfg.streammux_height = 720;
    }

    return cfg;
#endif
}

void validate_app_config_or_throw(const AppConfig& cfg) {
    if (cfg.input_url.empty()) {
        mantis::fail("CONFIG_SCHEMA", "input_url must not be empty");
    }
    if (cfg.tracker_config_path.empty()) {
        mantis::fail("CONFIG_SCHEMA", "tracker_config_path must not be empty");
    }
    if (!std::filesystem::exists(std::filesystem::path(cfg.tracker_config_path))) {
        mantis::fail("CONFIG_IO", "tracker config not found: '" + cfg.tracker_config_path + "'");
    }
    if (cfg.tracker_lib_path.empty()) {
        mantis::fail("CONFIG_SCHEMA", "tracker_lib_path must not be empty");
    }
    if (!std::filesystem::exists(std::filesystem::path(cfg.tracker_lib_path))) {
        mantis::fail("CONFIG_IO", "tracker library not found: '" + cfg.tracker_lib_path + "'");
    }
}

} // namespace

int run_detection_app(int argc, char** argv, PipelineVariant variant) {
    try {
        const auto cli = mantis::parse_cli_or_throw(argc, argv);
        auto cfg = load_app_config_or_throw(cli.config_file, variant);
        validate_app_config_or_throw(cfg);

        if (!cfg.object_detection_weight.empty()) {
            cfg.infer_config_path = mantis::apply_model_engine_file_to_infer_config_or_throw(
                cfg.infer_config_path,
                cfg.object_detection_weight,
                variant == PipelineVariant::kLlieObjectDetection ? "mantis_llie_object_detection" : "mantis_object_detection");
        }

        if (!cfg.labels.empty()) {
            const auto catalog = mantis::load_label_catalog_or_throw(cfg.label_file);
            const auto allowed = mantis::resolve_label_ids_or_throw(cfg.labels, catalog, "labels");
            cfg.infer_config_path = mantis::apply_filter_out_ids_to_infer_config_or_throw(
                cfg.infer_config_path,
                allowed,
                variant == PipelineVariant::kLlieObjectDetection ? "mantis_llie_object_detection" : "mantis_object_detection");
        }

        if (cli.validate_only) {
            std::cout << "config validation passed" << std::endl;
            return 0;
        }

        const std::string moth_path = mantis::write_moth_config_override_or_throw(
            cfg.moth_config_path,
            cfg.name,
            variant == PipelineVariant::kLlieObjectDetection ? "llie_object_detection" : "object_detection");

        PipelineOptions options;
        options.variant = variant;
        options.input_url = cfg.input_url;
        options.latency_ms = cfg.latency_ms;
        options.use_tcp = cfg.use_tcp;
        options.batch_size = cfg.batch_size;
        options.streammux_width = cfg.streammux_width;
        options.streammux_height = cfg.streammux_height;
        options.gpu_id = cfg.gpu_id;
        options.nvbuf_memory_type = cfg.nvbuf_memory_type;
        options.infer_config_path = cfg.infer_config_path;
        options.tracker_lib_path = cfg.tracker_lib_path;
        options.tracker_config_path = cfg.tracker_config_path;
        options.video_bitrate = cfg.video_bitrate;
        options.moth_config_path = moth_path;

        setenv("GST_DEBUG", "3,mothtcpsink:6,nvinfer:4,nvdsosd:4", TRUE);
        const auto pipeline = build_pipeline_description(options);
        return mantis::run_pipeline_or_throw(&argc, &argv, pipeline);
    } catch (const std::exception& e) {
        std::cerr << e.what() << std::endl;
        return 1;
    }
}

} // namespace mantis::elements::object_detection
