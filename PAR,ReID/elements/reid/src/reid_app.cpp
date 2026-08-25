#include <gst/app/gstappsink.h>
#include <gst/gst.h>

#include <algorithm>
#include <array>
#include <atomic>
#include <chrono>
#include <cmath>
#include <cctype>
#include <condition_variable>
#include <csignal>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <deque>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <mutex>
#include <optional>
#include <random>
#include <set>
#include <sstream>
#include <string>
#include <thread>
#include <tuple>
#include <unordered_map>
#include <vector>

#include "gstnvdsmeta.h"
#include "nvdsmeta.h"
#include "nvbufsurface.h"

#include <librdkafka/rdkafka.h>
#include "strict_config.h"
#include "event_builder.h"
#include "moth_config_overrides.h"

#if __has_include("nvds_obj_encode.h")
#include "nvds_obj_encode.h"
#endif

#ifndef NO_JSON_SUPPORT
#include <nlohmann/json.hpp>
using json = nlohmann::json;
#endif

namespace {

constexpr const char* kPayloadVersion = "v1";
constexpr const char* kElementVersion = "1.0.0";
constexpr const char* kElementNameDefault = "reid";

std::atomic<bool> g_should_quit{false};

void handle_signal(int signo) {
    std::cerr << "Signal " << signo << " received, shutting down" << std::endl;
    g_should_quit.store(true);
}

std::string trim(const std::string& input) {
    const auto start = input.find_first_not_of(" \t\r\n");
    if (start == std::string::npos) {
        return std::string();
    }
    const auto end = input.find_last_not_of(" \t\r\n");
    return input.substr(start, end - start + 1);
}

std::string to_lower(std::string value) {
    std::transform(value.begin(), value.end(), value.begin(), [](unsigned char c) {
        return static_cast<char>(std::tolower(c));
    });
    return value;
}

std::string read_env(const char* key) {
    if (!key) return std::string();
    const char* value = std::getenv(key);
    return value ? std::string(value) : std::string();
}

uint64_t fnv1a64(const std::string& value) {
    constexpr uint64_t kOffset = 1469598103934665603ULL;
    constexpr uint64_t kPrime = 1099511628211ULL;
    uint64_t hash = kOffset;
    for (unsigned char c : value) {
        hash ^= static_cast<uint64_t>(c);
        hash *= kPrime;
    }
    return hash;
}

std::string generate_uuid_v4() {
    static thread_local std::mt19937_64 rng{std::random_device{}()};
    std::array<uint8_t, 16> bytes{};
    for (size_t i = 0; i < bytes.size(); i += 8) {
        const uint64_t chunk = rng();
        std::memcpy(bytes.data() + i, &chunk, std::min<size_t>(8, bytes.size() - i));
    }
    bytes[6] = static_cast<uint8_t>((bytes[6] & 0x0F) | 0x40);
    bytes[8] = static_cast<uint8_t>((bytes[8] & 0x3F) | 0x80);

    std::ostringstream oss;
    oss << std::hex << std::nouppercase;
    for (size_t i = 0; i < bytes.size(); ++i) {
        oss.width(2);
        oss.fill('0');
        oss << static_cast<int>(bytes[i]);
        if (i == 3 || i == 5 || i == 7 || i == 9) {
            oss << '-';
        }
    }
    return oss.str();
}

std::string base64_encode(const uint8_t* data, size_t len) {
    static const char kTable[] =
        "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";

    std::string out;
    out.reserve(((len + 2) / 3) * 4);

    size_t i = 0;
    while (i + 2 < len) {
        const uint32_t triple = (static_cast<uint32_t>(data[i]) << 16) |
                                (static_cast<uint32_t>(data[i + 1]) << 8) |
                                static_cast<uint32_t>(data[i + 2]);
        out.push_back(kTable[(triple >> 18) & 0x3F]);
        out.push_back(kTable[(triple >> 12) & 0x3F]);
        out.push_back(kTable[(triple >> 6) & 0x3F]);
        out.push_back(kTable[triple & 0x3F]);
        i += 3;
    }

    if (i < len) {
        uint32_t triple = static_cast<uint32_t>(data[i]) << 16;
        if (i + 1 < len) {
            triple |= static_cast<uint32_t>(data[i + 1]) << 8;
        }
        out.push_back(kTable[(triple >> 18) & 0x3F]);
        out.push_back(kTable[(triple >> 12) & 0x3F]);
        if (i + 1 < len) {
            out.push_back(kTable[(triple >> 6) & 0x3F]);
            out.push_back('=');
        } else {
            out.push_back('=');
            out.push_back('=');
        }
    }

    return out;
}

struct KafkaConfig {
    bool enabled = false;
    std::string bootstrap_servers;
    std::string topic = "mantis.person.patch.events.v1";
    std::string client_id;
    std::string acks = "1";
    std::string compression = "lz4";
    int linger_ms = 5;
    int batch_num_messages = 1000;
    int message_timeout_ms = 2000;
    int queue_buffering_max_kbytes = 102400;
    int max_in_flight = 5;
};

struct PatchConfig {
    bool enabled = false;
    std::vector<std::string> labels = {"person"};
    std::vector<int> class_ids;
    double confidence_threshold = -1.0;
    int max_objects_per_frame = 50;
    int sampling_interval_ms = 0;
    int sampling_interval_frames = 0;
    int min_interval_ms_per_tracking_id = 250;
    int jpeg_quality = 85;
    size_t message_max_bytes = 512000;
    int resize_width = 0;
    int resize_height = 0;
    int max_side = 0;
};

struct AsyncConfig {
    size_t queue_size = 256;
    int sampling_interval_ms = 0;
    int appsink_max_buffers = 2;
};

struct AppConfig {
    std::string input_url;
    std::string infer_config_path = "/opt/mantis/runtime/elements/object_detection/configs/primary_infer_config.txt";
    std::string moth_config_path = "/opt/mantis/runtime/config_tcp.txt";
    std::string tracker_config_path =
        "/opt/mantis/runtime/elements/object_detection/configs/primary_tracker_config.txt";
    std::string tracker_lib_path =
        "/opt/nvidia/deepstream/deepstream/lib/libnvds_nvmultiobjecttracker.so";
    std::string name;

    int latency_ms = 200;
    bool use_tcp = true;
    int batch_size = 1;
    int streammux_width = 1920;
    int streammux_height = 1080;
    int gpu_id = 0;
    int nvbuf_memory_type = 0;
    double confidence_threshold = 0.5;
    bool emit_empty_frames = false;
    std::vector<std::string> labels;
    std::string label_file = "/opt/mantis/runtime/model_repository/rtdetr_trt/labels.txt";
    bool video_output = true;
    int video_bitrate = 2000000;
    bool osd_enable = true;

    std::string stream_id;
    std::string element_type;
    std::vector<std::array<int, 2>> watch_zone_points;

    AsyncConfig async;
    PatchConfig patch;
    KafkaConfig kafka;
};

struct Metrics {
    std::atomic<uint64_t> patch_events_encoded{0};
    std::atomic<uint64_t> patch_events_enqueued{0};
    std::atomic<uint64_t> patch_events_dropped_queue_full{0};
    std::atomic<uint64_t> patch_events_dropped_too_large{0};
    std::atomic<uint64_t> kafka_delivered{0};
    std::atomic<uint64_t> kafka_delivery_failed{0};
    std::atomic<uint64_t> kafka_internal_queue_depth{0};
};

struct EventPayload {
    std::string key;
    std::string value;
};

struct QueueState {
    std::mutex mutex;
    std::condition_variable cv;
    std::deque<EventPayload> items;
    size_t max_size = 0;
    std::atomic<uint64_t> dropped{0};
    bool stopping = false;
};

struct AsyncContext {
    AppConfig* cfg = nullptr;
    QueueState* queue = nullptr;
    Metrics* metrics = nullptr;
    std::vector<std::string>* label_catalog = nullptr;
    std::vector<int> patch_class_ids;
    std::unordered_map<uint64_t, std::chrono::steady_clock::time_point> last_sample;
    std::unordered_map<uint64_t, std::chrono::steady_clock::time_point> last_track_sample;
    std::unordered_map<uint64_t, uint64_t> last_track_frame;
    std::mutex sample_mutex;
    std::mutex track_frame_mutex;
#if defined(NVDS_OBJ_ENCODE_AVAILABLE)
    NvDsObjEncCtxHandle encoder_ctx = nullptr;
#endif
};

std::vector<std::string> load_label_catalog(const std::string& path) {
    std::vector<std::string> labels;
    if (path.empty()) {
        return labels;
    }

    std::ifstream file(path);
    if (!file) {
        std::cerr << "Error: failed to open label file '" << path << "'" << std::endl;
        return labels;
    }

    std::string line;
    while (std::getline(file, line)) {
        const std::string trimmed = trim(line);
        if (trimmed.empty()) continue;
        labels.emplace_back(trimmed);
    }
    return labels;
}

std::vector<int> resolve_class_ids_from_labels(
    const std::vector<std::string>& requested,
    const std::vector<std::string>& catalog,
    const std::string& label_kind) {
    std::vector<int> resolved;
    if (catalog.empty() || requested.empty()) {
        return resolved;
    }

    for (const auto& raw_label : requested) {
        const std::string trimmed = trim(raw_label);
        if (trimmed.empty()) continue;

        int numeric_id = -1;
        try {
            size_t pos = 0;
            numeric_id = std::stoi(trimmed, &pos);
            if (pos == trimmed.size() && numeric_id >= 0 && numeric_id < static_cast<int>(catalog.size())) {
                resolved.push_back(numeric_id);
                continue;
            }
        } catch (...) {
        }

        const std::string key = to_lower(trimmed);
        bool found = false;
        for (size_t i = 0; i < catalog.size(); ++i) {
            if (to_lower(trim(catalog[i])) == key) {
                resolved.push_back(static_cast<int>(i));
                found = true;
            }
        }
        if (!found) {
            std::cerr << "Warning: requested " << label_kind << " label '" << raw_label
                      << "' not found in label catalog" << std::endl;
        }
    }

    if (!resolved.empty()) {
        std::sort(resolved.begin(), resolved.end());
        resolved.erase(std::unique(resolved.begin(), resolved.end()), resolved.end());
    } else if (!requested.empty()) {
        std::cerr << "Error: no requested " << label_kind
                  << " labels resolved; label filtering cannot be applied" << std::endl;
    }

    return resolved;
}

std::vector<int> resolve_allowed_class_ids(const AppConfig& cfg, const std::vector<std::string>& catalog) {
    return resolve_class_ids_from_labels(cfg.labels, catalog, "inference");
}

std::vector<int> resolve_patch_class_ids(const PatchConfig& cfg, const std::vector<std::string>& catalog) {
    std::vector<int> resolved;
    if (!cfg.class_ids.empty()) {
        resolved = cfg.class_ids;
    }
    if (!cfg.labels.empty()) {
        auto from_labels = resolve_class_ids_from_labels(cfg.labels, catalog, "patch");
        resolved.insert(resolved.end(), from_labels.begin(), from_labels.end());
    }

    if (!resolved.empty()) {
        std::sort(resolved.begin(), resolved.end());
        resolved.erase(std::unique(resolved.begin(), resolved.end()), resolved.end());
    }
    return resolved;
}

std::vector<int> build_filter_out_class_ids(const std::vector<int>& allowed_ids, int total_classes) {
    if (allowed_ids.empty() || total_classes <= 0) {
        return {};
    }

    std::vector<bool> allowed(static_cast<size_t>(total_classes), false);
    for (int id : allowed_ids) {
        if (id < 0 || id >= total_classes) {
            std::cerr << "Error: allowed label id out of range: " << id
                      << ", num-detected-classes=" << total_classes << std::endl;
            return {};
        }
        allowed[static_cast<size_t>(id)] = true;
    }

    std::vector<int> filtered;
    filtered.reserve(static_cast<size_t>(total_classes));
    for (int id = 0; id < total_classes; ++id) {
        if (!allowed[static_cast<size_t>(id)]) filtered.push_back(id);
    }
    return filtered;
}

std::string join_class_ids(const std::vector<int>& ids) {
    if (ids.empty()) return std::string();
    std::ostringstream oss;
    for (size_t i = 0; i < ids.size(); ++i) {
        if (i > 0) oss << ';';
        oss << ids[i];
    }
    return oss.str();
}

bool parse_num_detected_classes_from_lines(
    const std::vector<std::string>& lines,
    int& out_total_classes) {
    for (const auto& src_line : lines) {
        const auto line = trim(src_line);
        if (line.empty()) continue;
        if (line[0] == '#') continue;
        if (line.rfind("num-detected-classes=", 0) != 0) continue;

        const auto value = trim(line.substr(std::string("num-detected-classes=").size()));
        if (value.empty()) {
            std::cerr << "Error: num-detected-classes is empty in infer config" << std::endl;
            return false;
        }
        try {
            size_t consumed = 0;
            const int total = std::stoi(value, &consumed);
            if (consumed != value.size() || total <= 0) {
                std::cerr << "Error: invalid num-detected-classes value: " << value << std::endl;
                return false;
            }
            out_total_classes = total;
            return true;
        } catch (...) {
            std::cerr << "Error: invalid num-detected-classes value: " << value << std::endl;
            return false;
        }
    }

    std::cerr << "Error: num-detected-classes not found in infer config" << std::endl;
    return false;
}

bool apply_label_filter_to_infer_config(AppConfig& cfg) {
    if (cfg.labels.empty()) {
        return true;
    }

    if (cfg.label_file.empty()) {
        std::cerr << "Error: label_file is not set while labels filter is requested" << std::endl;
        return false;
    }

    const auto catalog = load_label_catalog(cfg.label_file);
    if (catalog.empty()) {
        std::cerr << "Error: label catalog is empty; cannot apply label filtering" << std::endl;
        return false;
    }

    const auto allowed_ids = resolve_allowed_class_ids(cfg, catalog);
    if (allowed_ids.empty()) {
        return false;
    }

    std::ifstream in(cfg.infer_config_path);
    if (!in) {
        std::cerr << "Error: failed to open infer config at '" << cfg.infer_config_path << "'" << std::endl;
        return false;
    }

    std::vector<std::string> lines;
    std::string line;
    while (std::getline(in, line)) {
        lines.push_back(line);
    }

    int total_classes = 0;
    if (!parse_num_detected_classes_from_lines(lines, total_classes)) {
        return false;
    }

    const auto filter_out_ids = build_filter_out_class_ids(allowed_ids, total_classes);
    if (filter_out_ids.empty()) {
        return true;
    }

    const auto ts = std::chrono::steady_clock::now().time_since_epoch().count();
    std::filesystem::path tmp_path =
        std::filesystem::temp_directory_path() / ("mantis_reid_infer_" + std::to_string(ts) + ".cfg");
    std::ofstream out(tmp_path);
    if (!out) {
        std::cerr << "Error: failed to write filtered infer config at '" << tmp_path.string() << "'" << std::endl;
        return false;
    }

    const std::string filter_line = "filter-out-class-ids=" + join_class_ids(filter_out_ids);

    bool inserted = false;
    for (const auto& src_line : lines) {
        const std::string trimmed = trim(src_line);
        if (trimmed.rfind("filter-out-class-ids=", 0) == 0) {
            continue;
        }
        if (!inserted && trimmed.rfind("[class-attrs-all]", 0) == 0) {
            out << filter_line << "\n";
            inserted = true;
        }
        out << src_line << "\n";
    }

    if (!inserted) {
        out << filter_line << "\n";
    }

    cfg.infer_config_path = tmp_path.string();
    std::cout << "[reid] using filtered infer config: " << cfg.infer_config_path << std::endl;

    return true;
}

#ifndef NO_JSON_SUPPORT
void parse_patch_size(const json& value, PatchConfig& patch) {
    if (value.is_number_integer()) {
        patch.max_side = value.get<int>();
        return;
    }
    if (value.is_array() && value.size() == 2) {
        patch.resize_width = value.at(0).get<int>();
        patch.resize_height = value.at(1).get<int>();
        return;
    }
    if (value.is_object()) {
        if (value.contains("width")) patch.resize_width = value.at("width").get<int>();
        if (value.contains("height")) patch.resize_height = value.at("height").get<int>();
    }
}

void apply_patch_config(const json& j, PatchConfig& patch) {
    if (j.contains("enabled")) patch.enabled = j.at("enabled").get<bool>();
    if (j.contains("labels")) patch.labels = j.at("labels").get<std::vector<std::string>>();
    if (j.contains("class_ids")) patch.class_ids = j.at("class_ids").get<std::vector<int>>();
    if (j.contains("confidence_threshold")) {
        patch.confidence_threshold = j.at("confidence_threshold").get<double>();
    }
    if (j.contains("max_objects_per_frame")) {
        patch.max_objects_per_frame = j.at("max_objects_per_frame").get<int>();
    }
    if (j.contains("sampling_interval_ms")) {
        patch.sampling_interval_ms = j.at("sampling_interval_ms").get<int>();
    }
    if (j.contains("sampling_interval_frames")) {
        patch.sampling_interval_frames = j.at("sampling_interval_frames").get<int>();
    }
    if (j.contains("min_interval_ms_per_tracking_id")) {
        patch.min_interval_ms_per_tracking_id = j.at("min_interval_ms_per_tracking_id").get<int>();
    }
    if (j.contains("jpeg_quality")) patch.jpeg_quality = j.at("jpeg_quality").get<int>();
    if (j.contains("message_max_bytes")) {
        patch.message_max_bytes = j.at("message_max_bytes").get<size_t>();
    }
    if (j.contains("max_side")) patch.max_side = j.at("max_side").get<int>();
    if (j.contains("size")) parse_patch_size(j.at("size"), patch);
    if (j.contains("width")) patch.resize_width = j.at("width").get<int>();
    if (j.contains("height")) patch.resize_height = j.at("height").get<int>();
}

void apply_kafka_config(const json& j, KafkaConfig& kafka) {
    if (j.contains("enabled")) kafka.enabled = j.at("enabled").get<bool>();
    if (j.contains("bootstrap_servers")) kafka.bootstrap_servers = j.at("bootstrap_servers").get<std::string>();
    if (j.contains("topic")) kafka.topic = j.at("topic").get<std::string>();
    if (j.contains("client_id")) kafka.client_id = j.at("client_id").get<std::string>();
    if (j.contains("acks")) {
        if (j.at("acks").is_string()) {
            kafka.acks = j.at("acks").get<std::string>();
        } else if (j.at("acks").is_number_integer()) {
            kafka.acks = std::to_string(j.at("acks").get<int>());
        }
    }
    if (j.contains("compression")) kafka.compression = j.at("compression").get<std::string>();
    if (j.contains("linger_ms")) kafka.linger_ms = j.at("linger_ms").get<int>();
    if (j.contains("batch_num_messages")) kafka.batch_num_messages = j.at("batch_num_messages").get<int>();
    if (j.contains("message_timeout_ms")) kafka.message_timeout_ms = j.at("message_timeout_ms").get<int>();
    if (j.contains("queue_buffering_max_kbytes")) {
        kafka.queue_buffering_max_kbytes = j.at("queue_buffering_max_kbytes").get<int>();
    }
    if (j.contains("max_in_flight")) kafka.max_in_flight = j.at("max_in_flight").get<int>();
}

struct IntPoint {
    int64_t x = 0;
    int64_t y = 0;
};

IntPoint to_int_point(const std::array<int, 2>& point) {
    return IntPoint{static_cast<int64_t>(point[0]), static_cast<int64_t>(point[1])};
}

int64_t orientation(const IntPoint& a, const IntPoint& b, const IntPoint& c) {
    return (b.x - a.x) * (c.y - a.y) - (b.y - a.y) * (c.x - a.x);
}

bool on_segment(const IntPoint& a, const IntPoint& b, const IntPoint& c) {
    return c.x >= std::min(a.x, b.x) && c.x <= std::max(a.x, b.x) &&
           c.y >= std::min(a.y, b.y) && c.y <= std::max(a.y, b.y);
}

bool segments_intersect(const IntPoint& p1, const IntPoint& q1, const IntPoint& p2, const IntPoint& q2) {
    const auto o1 = orientation(p1, q1, p2);
    const auto o2 = orientation(p1, q1, q2);
    const auto o3 = orientation(p2, q2, p1);
    const auto o4 = orientation(p2, q2, q1);

    if (((o1 > 0 && o2 < 0) || (o1 < 0 && o2 > 0)) &&
        ((o3 > 0 && o4 < 0) || (o3 < 0 && o4 > 0))) {
        return true;
    }
    if (o1 == 0 && on_segment(p1, q1, p2)) return true;
    if (o2 == 0 && on_segment(p1, q1, q2)) return true;
    if (o3 == 0 && on_segment(p2, q2, p1)) return true;
    if (o4 == 0 && on_segment(p2, q2, q1)) return true;
    return false;
}

bool is_clockwise_image_polygon(const std::vector<std::array<int, 2>>& points) {
    int64_t twice_area = 0;
    for (size_t i = 0; i < points.size(); ++i) {
        const auto next = (i + 1) % points.size();
        twice_area += static_cast<int64_t>(points[i][0]) * static_cast<int64_t>(points[next][1]) -
                      static_cast<int64_t>(points[next][0]) * static_cast<int64_t>(points[i][1]);
    }
    return twice_area > 0;
}

bool has_self_intersection(const std::vector<std::array<int, 2>>& points) {
    const size_t n = points.size();
    for (size_t i = 0; i < n; ++i) {
        const auto a1 = to_int_point(points[i]);
        const auto a2 = to_int_point(points[(i + 1) % n]);
        for (size_t j = i + 1; j < n; ++j) {
            if (i == j || (i + 1) % n == j || i == (j + 1) % n) {
                continue;
            }
            const auto b1 = to_int_point(points[j]);
            const auto b2 = to_int_point(points[(j + 1) % n]);
            if (segments_intersect(a1, a2, b1, b2)) {
                return true;
            }
        }
    }
    return false;
}

bool validate_watch_zone_points(const std::vector<std::array<int, 2>>& points) {
    if (points.empty()) {
        return true;
    }
    if (points.size() < 3) {
        std::cerr << "Error: watch_zone_points must contain either 0 or at least 3 points" << std::endl;
        return false;
    }
    for (size_t i = 0; i < points.size(); ++i) {
        const int x = points[i][0];
        const int y = points[i][1];
        if (x < 0 || x > 1920) {
            std::cerr << "Error: watch_zone_points[" << i << "][0] must be between 0 and 1920" << std::endl;
            return false;
        }
        if (y < 0 || y > 1080) {
            std::cerr << "Error: watch_zone_points[" << i << "][1] must be between 0 and 1080" << std::endl;
            return false;
        }
    }
    if (!is_clockwise_image_polygon(points)) {
        std::cerr << "Error: watch_zone_points must be clockwise in image coordinates" << std::endl;
        return false;
    }
    if (has_self_intersection(points)) {
        std::cerr << "Error: watch_zone_points must not self-intersect" << std::endl;
        return false;
    }
    return true;
}
#endif

bool load_config(const std::string& config_arg, AppConfig& out, std::string& config_source) {
#ifdef NO_JSON_SUPPORT
    std::cerr << "JSON support is required for this strict configuration mode." << std::endl;
    return false;
#else
    out = AppConfig{};

    auto apply_json = [&](const json& j) {
        if (j.contains("input_url")) out.input_url = j.at("input_url").get<std::string>();
        if (j.contains("infer_config_path")) out.infer_config_path = j.at("infer_config_path").get<std::string>();
        if (j.contains("moth_config_path")) out.moth_config_path = j.at("moth_config_path").get<std::string>();
        if (j.contains("tracker_config_path")) {
            out.tracker_config_path = j.at("tracker_config_path").get<std::string>();
        }
        if (j.contains("tracker_lib_path")) {
            out.tracker_lib_path = j.at("tracker_lib_path").get<std::string>();
        }
        if (j.contains("latency_ms")) out.latency_ms = j.at("latency_ms").get<int>();
        if (j.contains("use_tcp")) out.use_tcp = j.at("use_tcp").get<bool>();
        if (j.contains("batch_size")) out.batch_size = j.at("batch_size").get<int>();
        if (j.contains("streammux_width")) out.streammux_width = j.at("streammux_width").get<int>();
        if (j.contains("streammux_height")) out.streammux_height = j.at("streammux_height").get<int>();
        if (j.contains("gpu_id")) out.gpu_id = j.at("gpu_id").get<int>();
        if (j.contains("nvbuf_memory_type")) out.nvbuf_memory_type = j.at("nvbuf_memory_type").get<int>();
        if (j.contains("confidence_threshold")) out.confidence_threshold = j.at("confidence_threshold").get<double>();
        if (j.contains("emit_empty_frames")) out.emit_empty_frames = j.at("emit_empty_frames").get<bool>();
        if (j.contains("labels")) out.labels = j.at("labels").get<std::vector<std::string>>();
        if (j.contains("label_file")) out.label_file = j.at("label_file").get<std::string>();
        if (j.contains("name")) out.name = j.at("name").get<std::string>();
        if (j.contains("video_output")) out.video_output = j.at("video_output").get<bool>();
        if (j.contains("video_bitrate")) out.video_bitrate = j.at("video_bitrate").get<int>();
        if (j.contains("osd_enable")) out.osd_enable = j.at("osd_enable").get<bool>();
        if (j.contains("stream_id")) out.stream_id = j.at("stream_id").get<std::string>();
        if (j.contains("type")) out.element_type = j.at("type").get<std::string>();
        if (j.contains("watch_zone_points")) {
            out.watch_zone_points = j.at("watch_zone_points").get<std::vector<std::array<int, 2>>>();
        }

        if (j.contains("sampling_interval_ms")) out.async.sampling_interval_ms = j.at("sampling_interval_ms").get<int>();
        if (j.contains("async_queue_size")) out.async.queue_size = j.at("async_queue_size").get<size_t>();
        if (j.contains("appsink_max_buffers")) out.async.appsink_max_buffers = j.at("appsink_max_buffers").get<int>();

        if (j.contains("patch") && j.at("patch").is_object()) {
            apply_patch_config(j.at("patch"), out.patch);
        }
        if (j.contains("kafka") && j.at("kafka").is_object()) {
            apply_kafka_config(j.at("kafka"), out.kafka);
        }
    };

    auto try_parse_json_file = [&](const std::string& path) -> bool {
        std::ifstream f(path);
        if (!f) return false;
        try {
            json j = json::parse(f);
            const json schema = mantis::load_json_file_or_throw(
                "/opt/mantis/runtime/schemas/elements/reid.schema.json",
                "reid schema");
            mantis::validate_json_against_schema_or_throw(j, schema, "root");
            apply_json(j);
            config_source = path;
            return true;
        } catch (const json::exception& e) {
            std::cerr << "Config Parsing Error: " << e.what() << std::endl;
            return false;
        }
    };

    if (!try_parse_json_file(config_arg)) {
        std::cerr << "Failed to open config file: " << config_arg << std::endl;
        return false;
    }

    if (out.input_url.empty()) {
        std::cerr << "config.input_url is required" << std::endl;
        return false;
    }

    return true;
#endif
}

bool validate_async_config(const AppConfig& cfg) {
    if (cfg.async.queue_size == 0) {
        std::cerr << "Error: async_queue_size must be greater than 0" << std::endl;
        return false;
    }
    if (cfg.async.appsink_max_buffers <= 0) {
        std::cerr << "Error: appsink_max_buffers must be greater than 0" << std::endl;
        return false;
    }
#ifndef NO_JSON_SUPPORT
    if (!validate_watch_zone_points(cfg.watch_zone_points)) {
        return false;
    }
#endif
    if (cfg.patch.enabled) {
        if (cfg.patch.max_objects_per_frame <= 0) {
            std::cerr << "Error: patch_max_objects_per_frame must be greater than 0" << std::endl;
            return false;
        }
        if (cfg.patch.sampling_interval_frames < 0) {
            std::cerr << "Error: patch_sampling_interval_frames must be >= 0" << std::endl;
            return false;
        }
        if (cfg.patch.jpeg_quality <= 0 || cfg.patch.jpeg_quality > 100) {
            std::cerr << "Error: patch_jpeg_quality must be between 1 and 100" << std::endl;
            return false;
        }
        if (cfg.patch.message_max_bytes == 0) {
            std::cerr << "Error: patch_message_max_bytes must be greater than 0" << std::endl;
            return false;
        }
    }
    if (cfg.kafka.enabled) {
        if (cfg.kafka.bootstrap_servers.empty()) {
            std::cerr << "Error: kafka.bootstrap_servers is required when kafka is enabled" << std::endl;
            return false;
        }
        if (cfg.kafka.topic.empty()) {
            std::cerr << "Error: kafka.topic is required when kafka is enabled" << std::endl;
            return false;
        }
        if (cfg.kafka.client_id.empty()) {
            std::cerr << "Error: kafka.client_id is required when kafka is enabled" << std::endl;
            return false;
        }
    }
    if (cfg.patch.enabled && !cfg.kafka.enabled) {
        std::cerr << "Error: patch.enabled requires kafka.enabled" << std::endl;
        return false;
    }
    if (cfg.kafka.enabled && !cfg.patch.enabled) {
        std::cerr << "Error: kafka.enabled requires patch.enabled" << std::endl;
        return false;
    }
    return true;
}

bool enqueue_event(QueueState& queue, EventPayload payload) {
    std::lock_guard<std::mutex> lock(queue.mutex);
    if (queue.items.size() >= queue.max_size) {
        queue.dropped.fetch_add(1, std::memory_order_relaxed);
        return false;
    }
    queue.items.emplace_back(std::move(payload));
    queue.cv.notify_one();
    return true;
}

std::optional<EventPayload> pop_event(QueueState& queue) {
    std::unique_lock<std::mutex> lock(queue.mutex);
    queue.cv.wait(lock, [&]() { return queue.stopping || !queue.items.empty(); });
    if (queue.items.empty()) {
        return std::nullopt;
    }
    EventPayload payload = std::move(queue.items.front());
    queue.items.pop_front();
    return payload;
}

uint64_t resolve_timestamp_ns(const NvDsFrameMeta* frame_meta) {
    if (!frame_meta) return 0;
    uint64_t ts = frame_meta->ntp_timestamp;
    if (ts != 0) return ts;
    if (frame_meta->buf_pts != 0) return static_cast<uint64_t>(frame_meta->buf_pts);
    return static_cast<uint64_t>(
        std::chrono::duration_cast<std::chrono::nanoseconds>(
            std::chrono::system_clock::now().time_since_epoch())
            .count());
}

bool should_sample_interval(
    std::unordered_map<uint64_t, std::chrono::steady_clock::time_point>& last_map,
    std::mutex& mutex,
    uint64_t key,
    int interval_ms) {
    if (interval_ms <= 0) {
        return true;
    }
    const auto now = std::chrono::steady_clock::now();
    std::lock_guard<std::mutex> lock(mutex);
    auto it = last_map.find(key);
    if (it == last_map.end()) {
        last_map.emplace(key, now);
        return true;
    }
    const auto elapsed = std::chrono::duration_cast<std::chrono::milliseconds>(now - it->second).count();
    if (elapsed >= interval_ms) {
        it->second = now;
        return true;
    }
    return false;
}

bool should_sample_frame_interval(
    std::unordered_map<uint64_t, uint64_t>& last_map,
    std::mutex& mutex,
    uint64_t key,
    uint64_t frame_num,
    int interval_frames) {
    if (interval_frames <= 0) {
        return true;
    }
    std::unique_lock<std::mutex> lock(mutex, std::try_to_lock);
    if (!lock.owns_lock()) {
        return true;
    }
    auto it = last_map.find(key);
    if (it == last_map.end()) {
        last_map.emplace(key, frame_num);
        return true;
    }
    if (frame_num >= it->second + static_cast<uint64_t>(interval_frames)) {
        it->second = frame_num;
        return true;
    }
    return false;
}

bool is_allowed_class(const std::vector<int>& allowed, int class_id) {
    if (allowed.empty()) {
        return true;
    }
    return std::binary_search(allowed.begin(), allowed.end(), class_id);
}

bool resolve_patch_dimensions(
    const PatchConfig& patch,
    float bbox_width,
    float bbox_height,
    int frame_width,
    int frame_height,
    int& out_width,
    int& out_height,
    bool& out_scale) {
    const int crop_w = static_cast<int>(std::round(bbox_width));
    const int crop_h = static_cast<int>(std::round(bbox_height));
    if (crop_w <= 0 || crop_h <= 0) {
        return false;
    }

    out_width = crop_w;
    out_height = crop_h;
    out_scale = false;

    if (patch.resize_width > 0 && patch.resize_height > 0) {
        out_width = patch.resize_width;
        out_height = patch.resize_height;
        out_scale = true;
    } else if (patch.max_side > 0) {
        const int current_max = std::max(crop_w, crop_h);
        if (current_max > patch.max_side) {
            const float scale = static_cast<float>(patch.max_side) / static_cast<float>(current_max);
            out_width = std::max(1, static_cast<int>(std::round(crop_w * scale)));
            out_height = std::max(1, static_cast<int>(std::round(crop_h * scale)));
            out_scale = true;
        }
    }

    if (frame_width > 0) {
        out_width = std::min(out_width, frame_width);
    }
    if (frame_height > 0) {
        out_height = std::min(out_height, frame_height);
    }

    if (out_width <= 0 || out_height <= 0) {
        return false;
    }

    return true;
}

GstFlowReturn handle_patch_sample(GstAppSink* sink, AsyncContext* ctx) {
#ifndef NO_JSON_SUPPORT
    GstSample* sample = gst_app_sink_pull_sample(sink);
    if (!sample) {
        return GST_FLOW_OK;
    }

    GstBuffer* buffer = gst_sample_get_buffer(sample);
    if (!buffer) {
        gst_sample_unref(sample);
        return GST_FLOW_OK;
    }

    NvDsBatchMeta* batch_meta = gst_buffer_get_nvds_batch_meta(buffer);
    if (!batch_meta) {
        gst_sample_unref(sample);
        return GST_FLOW_OK;
    }

    GstMapInfo map_info{};
    if (!gst_buffer_map(buffer, &map_info, GST_MAP_READ)) {
        gst_sample_unref(sample);
        return GST_FLOW_OK;
    }

    auto* surface = reinterpret_cast<NvBufSurface*>(map_info.data);
    if (!surface) {
        gst_buffer_unmap(buffer, &map_info);
        gst_sample_unref(sample);
        return GST_FLOW_OK;
    }

    for (NvDsMetaList* l_frame = batch_meta->frame_meta_list; l_frame != nullptr; l_frame = l_frame->next) {
        auto* frame_meta = static_cast<NvDsFrameMeta*>(l_frame->data);
        if (!frame_meta) {
            continue;
        }

        const uint64_t source_key = fnv1a64(ctx->cfg->stream_id);
        if (!should_sample_interval(ctx->last_sample, ctx->sample_mutex, source_key, ctx->cfg->patch.sampling_interval_ms)) {
            continue;
        }

#if !defined(NVDS_OBJ_ENCODE_AVAILABLE)
        (void)frame_meta;
        continue;
#else
        std::vector<std::tuple<NvDsObjectMeta*, int, int>> encoded_objects;
        encoded_objects.reserve(static_cast<size_t>(ctx->cfg->patch.max_objects_per_frame));

        int object_count = 0;
        for (NvDsMetaList* l_obj = frame_meta->obj_meta_list; l_obj != nullptr; l_obj = l_obj->next) {
            if (object_count >= ctx->cfg->patch.max_objects_per_frame) {
                break;
            }

            auto* obj_meta = static_cast<NvDsObjectMeta*>(l_obj->data);
            if (!obj_meta) {
                continue;
            }

            if (!is_allowed_class(ctx->patch_class_ids, obj_meta->class_id)) {
                continue;
            }

            const double threshold = ctx->cfg->patch.confidence_threshold >= 0.0
                ? ctx->cfg->patch.confidence_threshold
                : ctx->cfg->confidence_threshold;
            if (obj_meta->confidence < threshold) {
                continue;
            }

            const bool has_track = (obj_meta->object_id != UNTRACKED_OBJECT_ID);
            uint64_t track_key = 0;
            if (has_track) {
                track_key = source_key ^ static_cast<uint64_t>(obj_meta->object_id);
            }

            if (has_track && ctx->cfg->patch.min_interval_ms_per_tracking_id > 0) {
                if (!should_sample_interval(
                        ctx->last_track_sample,
                        ctx->sample_mutex,
                        track_key,
                        ctx->cfg->patch.min_interval_ms_per_tracking_id)) {
                    continue;
                }
            }

            if (has_track && ctx->cfg->patch.sampling_interval_frames > 0) {
                if (!should_sample_frame_interval(
                        ctx->last_track_frame,
                        ctx->track_frame_mutex,
                        track_key,
                        static_cast<uint64_t>(frame_meta->frame_num),
                        ctx->cfg->patch.sampling_interval_frames)) {
                    continue;
                }
            }

            int patch_w = 0;
            int patch_h = 0;
            bool scale = false;
            if (!resolve_patch_dimensions(
                    ctx->cfg->patch,
                    obj_meta->rect_params.width,
                    obj_meta->rect_params.height,
                    static_cast<int>(frame_meta->source_frame_width),
                    static_cast<int>(frame_meta->source_frame_height),
                    patch_w,
                    patch_h,
                    scale)) {
                continue;
            }

            NvDsObjEncUsrArgs args{};
            args.saveImg = false;
            args.attachUsrMeta = true;
            args.quality = ctx->cfg->patch.jpeg_quality;
            args.isFrame = false;
            args.calcEncodeTime = false;
            args.objNum = object_count;
            if (scale) {
                args.scaleImg = true;
                args.scaledWidth = static_cast<uint32_t>(patch_w);
                args.scaledHeight = static_cast<uint32_t>(patch_h);
            }

            if (!nvds_obj_enc_process(ctx->encoder_ctx, &args, surface, obj_meta, frame_meta)) {
                continue;
            }

            encoded_objects.emplace_back(obj_meta, patch_w, patch_h);
            object_count++;
        }

        if (encoded_objects.empty()) {
            continue;
        }

        nvds_obj_enc_finish(ctx->encoder_ctx);

        for (const auto& [obj_meta, patch_w, patch_h] : encoded_objects) {
            NvDsObjEncOutParams* enc_params = nullptr;
            for (NvDsMetaList* l_user = obj_meta->obj_user_meta_list; l_user != nullptr; l_user = l_user->next) {
                auto* user_meta = static_cast<NvDsUserMeta*>(l_user->data);
                if (user_meta && user_meta->base_meta.meta_type == NVDS_CROP_IMAGE_META) {
                    enc_params = static_cast<NvDsObjEncOutParams*>(user_meta->user_meta_data);
                    break;
                }
            }

            if (!enc_params || !enc_params->outBuffer || enc_params->outLen == 0) {
                continue;
            }

            ctx->metrics->patch_events_encoded.fetch_add(1, std::memory_order_relaxed);

            json event;
            event["version"] = kPayloadVersion;
            event["event_id"] = generate_uuid_v4();
            event["stream_id"] = ctx->cfg->stream_id;
            event["frame_id"] = frame_meta->frame_num;
            event["timestamp_ns"] = resolve_timestamp_ns(frame_meta);
            json frame_size;
            frame_size["width"] = static_cast<int>(frame_meta->source_frame_width);
            frame_size["height"] = static_cast<int>(frame_meta->source_frame_height);
            event["frame_size"] = frame_size;
            json watch_zone_points = json::array();
            for (const auto& point : ctx->cfg->watch_zone_points) {
                watch_zone_points.push_back(json::array({point[0], point[1]}));
            }
            event["watch_zone_points"] = watch_zone_points;

            json obj;
            obj["class_id"] = obj_meta->class_id;
            if (ctx->label_catalog &&
                obj_meta->class_id >= 0 &&
                static_cast<size_t>(obj_meta->class_id) < ctx->label_catalog->size()) {
                obj["label"] = (*ctx->label_catalog)[static_cast<size_t>(obj_meta->class_id)];
            }
            if (obj_meta->object_id != UNTRACKED_OBJECT_ID) {
                obj["tracking_id"] = obj_meta->object_id;
            }
            obj["confidence"] = obj_meta->confidence;
            json bbox;
            bbox["left"] = obj_meta->rect_params.left;
            bbox["top"] = obj_meta->rect_params.top;
            bbox["width"] = obj_meta->rect_params.width;
            bbox["height"] = obj_meta->rect_params.height;
            obj["bbox"] = bbox;
            event["object"] = obj;

            json patch;
            patch["format"] = "jpeg";
            patch["width"] = patch_w;
            patch["height"] = patch_h;
            patch["bytes_b64"] = base64_encode(enc_params->outBuffer, enc_params->outLen);
            event["patch"] = patch;

            json meta;
            meta["source"] = kElementNameDefault;
            meta["element_version"] = kElementVersion;
            meta["sampling_interval_ms"] = ctx->cfg->patch.sampling_interval_ms;
            meta["sampling_interval_frames"] = ctx->cfg->patch.sampling_interval_frames;
            event["meta"] = meta;

            std::string payload = event.dump();
            if (payload.size() > ctx->cfg->patch.message_max_bytes) {
                ctx->metrics->patch_events_dropped_too_large.fetch_add(1, std::memory_order_relaxed);
                continue;
            }

            std::string tracking_key = (obj_meta->object_id != UNTRACKED_OBJECT_ID)
                ? std::to_string(obj_meta->object_id)
                : std::string("untracked");
            std::string key = mantis::elements::reid::build_tracking_key(
                ctx->cfg->stream_id,
                tracking_key);

            if (enqueue_event(*ctx->queue, EventPayload{std::move(key), std::move(payload)})) {
                ctx->metrics->patch_events_enqueued.fetch_add(1, std::memory_order_relaxed);
            } else {
                ctx->metrics->patch_events_dropped_queue_full.fetch_add(1, std::memory_order_relaxed);
            }
        }
#endif
    }

    gst_buffer_unmap(buffer, &map_info);
    gst_sample_unref(sample);
#else
    (void)sink;
    (void)ctx;
#endif
    return GST_FLOW_OK;
}

GstFlowReturn handle_appsink_sample(GstAppSink* sink, gpointer user_data) {
    auto* ctx = static_cast<AsyncContext*>(user_data);
    if (!ctx || !ctx->cfg || !ctx->queue) {
        return GST_FLOW_OK;
    }

    if (!ctx->cfg->patch.enabled || !ctx->cfg->kafka.enabled) {
        std::cerr << "Error: patch.enabled and kafka.enabled must both be true" << std::endl;
        return GST_FLOW_ERROR;
    }

    return handle_patch_sample(sink, ctx);
}

void kafka_delivery_callback(rd_kafka_t* rk, const rd_kafka_message_t* msg, void* opaque) {
    (void)rk;
    auto* metrics = static_cast<Metrics*>(opaque);
    if (!metrics) return;
    if (msg->err) {
        metrics->kafka_delivery_failed.fetch_add(1, std::memory_order_relaxed);
    } else {
        metrics->kafka_delivered.fetch_add(1, std::memory_order_relaxed);
    }
}

bool configure_kafka_conf(rd_kafka_conf_t* conf, const std::string& key, const std::string& value) {
    char errstr[512];
    if (rd_kafka_conf_set(conf, key.c_str(), value.c_str(), errstr, sizeof(errstr)) != RD_KAFKA_CONF_OK) {
        std::cerr << "Error: kafka config " << key << " failed: " << errstr << std::endl;
        return false;
    }
    return true;
}

rd_kafka_t* create_kafka_producer(const KafkaConfig& cfg, Metrics& metrics) {
    rd_kafka_conf_t* conf = rd_kafka_conf_new();
    if (!configure_kafka_conf(conf, "bootstrap.servers", cfg.bootstrap_servers)) {
        rd_kafka_conf_destroy(conf);
        return nullptr;
    }
    if (!cfg.client_id.empty()) {
        if (!configure_kafka_conf(conf, "client.id", cfg.client_id)) {
            rd_kafka_conf_destroy(conf);
            return nullptr;
        }
    }
    if (!configure_kafka_conf(conf, "acks", cfg.acks) ||
        !configure_kafka_conf(conf, "compression.type", cfg.compression) ||
        !configure_kafka_conf(conf, "linger.ms", std::to_string(cfg.linger_ms)) ||
        !configure_kafka_conf(conf, "batch.num.messages", std::to_string(cfg.batch_num_messages)) ||
        !configure_kafka_conf(conf, "message.timeout.ms", std::to_string(cfg.message_timeout_ms)) ||
        !configure_kafka_conf(conf, "queue.buffering.max.kbytes", std::to_string(cfg.queue_buffering_max_kbytes)) ||
        !configure_kafka_conf(conf, "max.in.flight.requests.per.connection", std::to_string(cfg.max_in_flight))) {
        rd_kafka_conf_destroy(conf);
        return nullptr;
    }

    rd_kafka_conf_set_dr_msg_cb(conf, kafka_delivery_callback);
    rd_kafka_conf_set_opaque(conf, &metrics);

    char errstr[512];
    rd_kafka_t* rk = rd_kafka_new(RD_KAFKA_PRODUCER, conf, errstr, sizeof(errstr));
    if (!rk) {
        std::cerr << "Error: failed to create Kafka producer: " << errstr << std::endl;
        return nullptr;
    }
    return rk;
}

void kafka_producer_loop(rd_kafka_t* rk, const KafkaConfig& cfg, QueueState& queue, Metrics& metrics) {
    auto last_log = std::chrono::steady_clock::now();

    while (true) {
        auto payload_opt = pop_event(queue);
        if (!payload_opt.has_value()) {
            if (queue.stopping) {
                break;
            }
            continue;
        }

        const auto& payload = payload_opt.value();
        rd_kafka_resp_err_t err = rd_kafka_producev(
            rk,
            RD_KAFKA_V_TOPIC(cfg.topic.c_str()),
            RD_KAFKA_V_VALUE(const_cast<void*>(static_cast<const void*>(payload.value.data())), payload.value.size()),
            RD_KAFKA_V_KEY(const_cast<void*>(static_cast<const void*>(payload.key.data())), payload.key.size()),
            RD_KAFKA_V_MSGFLAGS(RD_KAFKA_MSG_F_COPY),
            RD_KAFKA_V_END);
        if (err != RD_KAFKA_RESP_ERR_NO_ERROR) {
            metrics.kafka_delivery_failed.fetch_add(1, std::memory_order_relaxed);
            std::cerr << "Kafka produce failed: " << rd_kafka_err2str(err) << std::endl;
        }

        rd_kafka_poll(rk, 0);
        metrics.kafka_internal_queue_depth.store(rd_kafka_outq_len(rk), std::memory_order_relaxed);

        const auto now = std::chrono::steady_clock::now();
        if (std::chrono::duration_cast<std::chrono::seconds>(now - last_log).count() >= 5) {
            last_log = now;
            std::cout << "[reid] stats "
                      << "encoded=" << metrics.patch_events_encoded.load() << " "
                      << "enqueued=" << metrics.patch_events_enqueued.load() << " "
                      << "dropped_full=" << metrics.patch_events_dropped_queue_full.load() << " "
                      << "dropped_large=" << metrics.patch_events_dropped_too_large.load() << " "
                      << "kafka_delivered=" << metrics.kafka_delivered.load() << " "
                      << "kafka_failed=" << metrics.kafka_delivery_failed.load() << " "
                      << "kafka_outq=" << metrics.kafka_internal_queue_depth.load()
                      << std::endl;
        }
    }

    rd_kafka_flush(rk, 2000);
}

std::string build_pipeline_description(const AppConfig& cfg, const std::string& moth_config_path) {
    const std::string protocol = cfg.use_tcp ? "tcp" : "udp";

    std::ostringstream desc;
    desc << "rtspsrc location=" << cfg.input_url
         << " protocols=" << protocol
         << " latency=" << cfg.latency_ms
         << " drop-on-latency=false ! "
         << "rtph264depay ! "
         << "h264parse config-interval=-1 disable-passthrough=true ! "
         << "video/x-h264,alignment=au ! "
         << "nvv4l2decoder gpu-id=" << cfg.gpu_id << " ! "
         << "queue name=queue-post-decode max-size-buffers=1 leaky=2 ! "
         << "streammux.sink_0 "
         << "nvstreammux name=streammux "
         << "batch-size=" << cfg.batch_size << " "
         << "width=" << cfg.streammux_width << " "
         << "height=" << cfg.streammux_height << " "
         << "live-source=false "
         << "batched-push-timeout=40000 "
         << "gpu-id=" << cfg.gpu_id << " "
         << "nvbuf-memory-type=" << cfg.nvbuf_memory_type << " ! "
         << "nvinfer name=primary-infer "
         << "config-file-path=" << cfg.infer_config_path << " "
         << "batch-size=" << cfg.batch_size << " "
         << "gpu-id=" << cfg.gpu_id << " ! "
         << "nvtracker name=tracker "
         << "ll-lib-file=" << cfg.tracker_lib_path << " "
         << "ll-config-file=" << cfg.tracker_config_path << " "
         << "gpu-id=" << cfg.gpu_id << " "
         << "tracker-width=640 "
         << "tracker-height=384 "
         << "display-tracking-id=1 ! "
         << "tee name=odtee ";

    desc << "odtee. ! queue name=queue-async max-size-buffers=1 leaky=2 ! "
         << "appsink name=async_sink emit-signals=false sync=false drop=true max-buffers="
         << cfg.async.appsink_max_buffers << " ";

    desc << "odtee. ! queue name=queue-video max-size-buffers=1 leaky=0 ! "
         << "nvvideoconvert name=nvvidconv-pre-osd "
         << "gpu-id=" << cfg.gpu_id << " "
         << "nvbuf-memory-type=" << cfg.nvbuf_memory_type << " ! "
         << "video/x-raw(memory:NVMM),format=RGBA ! "
         << "nvdsosd name=osd gpu-id=" << cfg.gpu_id << " ! "
         << "nvvideoconvert name=nvvidconv-post "
         << "gpu-id=" << cfg.gpu_id << " "
         << "nvbuf-memory-type=" << cfg.nvbuf_memory_type << " ! "
         << "video/x-raw(memory:NVMM),format=NV12 ! "
         << "queue name=queue-enc max-size-buffers=1 leaky=0 ! "
         << "nvv4l2h264enc name=encoder insert-sps-pps=true bitrate=" << cfg.video_bitrate
         << " gpu-id=" << cfg.gpu_id << " ! "
         << "h264parse name=parser-enc config-interval=1 ! "
         << "mothtcpsink name=moth-sink config-path=" << moth_config_path;

    return desc.str();
}

} // namespace

int run_reid_app(int argc, char** argv) {
    std::signal(SIGINT, handle_signal);
    std::signal(SIGTERM, handle_signal);

    std::string config_file_path;
    bool validate_config_only = false;
    for (int i = 1; i < argc; ++i) {
        std::string arg = argv[i];
        if (arg == "--config-file" && i + 1 < argc) {
            config_file_path = argv[++i];
        } else if (arg == "--validate-config") {
            validate_config_only = true;
        } else {
            std::cerr << "Unsupported argument: " << arg << std::endl;
            return 1;
        }
    }

    if (config_file_path.empty()) {
        std::cerr << "Usage: " << argv[0] << " --config-file <json_path> [--validate-config]" << std::endl;
        return 1;
    }

    AppConfig cfg;
    std::string config_source;
    if (!load_config(config_file_path, cfg, config_source)) {
        return 1;
    }

    if (!validate_async_config(cfg)) {
        return 1;
    }

#if !defined(NVDS_OBJ_ENCODE_AVAILABLE)
    if (cfg.patch.enabled) {
        std::cerr << "Error: nvds_obj_encode is not available in this build" << std::endl;
        return 1;
    }
#endif

    if (cfg.stream_id.empty()) {
        std::cerr << "Error: stream_id is required explicitly in config" << std::endl;
        return 1;
    }
    if (cfg.element_type.empty()) {
        std::cerr << "Error: type is required explicitly in config" << std::endl;
        return 1;
    }

    if (!cfg.kafka.enabled) {
        std::cerr << "Error: kafka.enabled must be true; implicit log sink fallback is removed" << std::endl;
        return 1;
    }

    if (validate_config_only) {
        std::cout << "config validation passed" << std::endl;
        return 0;
    }

    setenv("GST_DEBUG", "3,mothtcpsink:6,nvinfer:4,nvdsosd:4", TRUE);
    gst_init(&argc, &argv);

    std::string moth_config_path;
    try {
        moth_config_path =
            mantis::write_moth_config_override_or_throw(cfg.moth_config_path, cfg.name, "reid");
    } catch (const std::exception& exc) {
        std::cerr << "Failed to prepare moth config override: " << exc.what() << std::endl;
        return 1;
    }
    if (moth_config_path != cfg.moth_config_path) {
        std::cout << "[reid] using moth config: " << moth_config_path << std::endl;
    }

    if (cfg.tracker_config_path.empty()) {
        std::cerr << "Error: tracker_config_path is not set" << std::endl;
        return 1;
    }
    {
        std::ifstream tracker_cfg(cfg.tracker_config_path);
        if (!tracker_cfg) {
            std::cerr << "Error: failed to open tracker config at '" << cfg.tracker_config_path << "'" << std::endl;
            return 1;
        }
    }

    if (cfg.tracker_lib_path.empty()) {
        std::cerr << "Error: tracker_lib_path is not set" << std::endl;
        return 1;
    }
    if (!std::filesystem::exists(std::filesystem::path(cfg.tracker_lib_path))) {
        std::cerr << "Error: nvtracker library not found at '" << cfg.tracker_lib_path << "'" << std::endl;
        return 1;
    }

    if (!apply_label_filter_to_infer_config(cfg)) {
        return 1;
    }

    std::vector<std::string> label_catalog = load_label_catalog(cfg.label_file);

    AsyncContext ctx;
    ctx.cfg = &cfg;
    ctx.label_catalog = &label_catalog;

    if (cfg.patch.enabled) {
        ctx.patch_class_ids = resolve_patch_class_ids(cfg.patch, label_catalog);
        if (ctx.patch_class_ids.empty()) {
            std::cerr << "Error: patch labels/class_ids could not be resolved" << std::endl;
            return 1;
        }
    }

    QueueState queue;
    queue.max_size = cfg.async.queue_size;
    queue.dropped.store(0, std::memory_order_relaxed);
    queue.stopping = false;
    ctx.queue = &queue;

    Metrics metrics;
    ctx.metrics = &metrics;

#if defined(NVDS_OBJ_ENCODE_AVAILABLE)
    if (cfg.patch.enabled) {
        ctx.encoder_ctx = nvds_obj_enc_create_context(cfg.gpu_id);
        if (!ctx.encoder_ctx) {
            std::cerr << "Error: failed to create NvDs object encoder context" << std::endl;
            return 1;
        }
    }
#endif

    std::thread worker_thread;
    rd_kafka_t* kafka_producer = nullptr;

    if (cfg.stream_id.empty()) {
        std::cerr << "Error: stream_id must be set when Kafka is enabled" << std::endl;
        return 1;
    }
    kafka_producer = create_kafka_producer(cfg.kafka, metrics);
    if (!kafka_producer) {
        return 1;
    }
    worker_thread = std::thread(kafka_producer_loop, kafka_producer, std::ref(cfg.kafka), std::ref(queue), std::ref(metrics));

    const std::string pipeline_description = build_pipeline_description(cfg, moth_config_path);

    std::cout << "[reid] gst pipeline: " << pipeline_description << std::endl;

    GError* error = nullptr;
    GstElement* pipeline = gst_parse_launch(pipeline_description.c_str(), &error);
    if (!pipeline) {
        if (error) {
            std::cerr << "Failed to create pipeline: " << error->message << std::endl;
            g_error_free(error);
        } else {
            std::cerr << "Failed to create pipeline" << std::endl;
        }
        queue.stopping = true;
        queue.cv.notify_all();
        if (worker_thread.joinable()) {
            worker_thread.join();
        }
        if (kafka_producer) {
            rd_kafka_destroy(kafka_producer);
        }
#if defined(NVDS_OBJ_ENCODE_AVAILABLE)
        if (ctx.encoder_ctx) {
            nvds_obj_enc_destroy_context(ctx.encoder_ctx);
        }
#endif
        return 1;
    }

    GstElement* appsink = gst_bin_get_by_name(GST_BIN(pipeline), "async_sink");
    if (appsink) {
        GstAppSinkCallbacks callbacks = {};
        callbacks.new_sample = handle_appsink_sample;
        gst_app_sink_set_callbacks(GST_APP_SINK(appsink), &callbacks, &ctx, nullptr);
        gst_object_unref(appsink);
    } else {
        std::cerr << "Error: appsink element not found in pipeline" << std::endl;
        queue.stopping = true;
        queue.cv.notify_all();
        if (worker_thread.joinable()) {
            worker_thread.join();
        }
        if (kafka_producer) {
            rd_kafka_destroy(kafka_producer);
        }
#if defined(NVDS_OBJ_ENCODE_AVAILABLE)
        if (ctx.encoder_ctx) {
            nvds_obj_enc_destroy_context(ctx.encoder_ctx);
        }
#endif
        gst_element_set_state(pipeline, GST_STATE_NULL);
        gst_object_unref(pipeline);
        return 1;
    }

    std::cout << "Starting pipeline..." << std::endl;
    std::cout << "Main Config: " << (config_source.empty() ? config_file_path : config_source) << std::endl;
    std::cout << "Infer Config: " << cfg.infer_config_path << std::endl;
    std::cout << "Moth Config: " << moth_config_path << std::endl;
    if (cfg.kafka.enabled) {
        std::cout << "Kafka: " << cfg.kafka.bootstrap_servers << " topic=" << cfg.kafka.topic << std::endl;
    }

    gst_element_set_state(pipeline, GST_STATE_PLAYING);
    GstBus* bus = gst_element_get_bus(pipeline);

    while (!g_should_quit.load()) {
        GstMessage* msg = gst_bus_timed_pop_filtered(bus, 500 * GST_MSECOND,
            static_cast<GstMessageType>(GST_MESSAGE_ERROR | GST_MESSAGE_EOS));

        if (msg) {
            switch (GST_MESSAGE_TYPE(msg)) {
                case GST_MESSAGE_ERROR: {
                    GError* err = nullptr;
                    gchar* debug = nullptr;
                    gst_message_parse_error(msg, &err, &debug);
                    std::cerr << "Error: " << (err ? err->message : "unknown") << std::endl;
                    if (debug) std::cerr << "Debug: " << debug << std::endl;
                    g_error_free(err);
                    g_free(debug);
                    g_should_quit.store(true);
                    break;
                }
                case GST_MESSAGE_EOS:
                    std::cout << "EOS received." << std::endl;
                    g_should_quit.store(true);
                    break;
                default:
                    break;
            }
            gst_message_unref(msg);
        }
    }

    gst_element_set_state(pipeline, GST_STATE_NULL);
    if (bus) gst_object_unref(bus);
    if (pipeline) gst_object_unref(pipeline);

    {
        std::lock_guard<std::mutex> lock(queue.mutex);
        queue.stopping = true;
    }
    queue.cv.notify_all();
    if (worker_thread.joinable()) {
        worker_thread.join();
    }
    if (kafka_producer) {
        rd_kafka_destroy(kafka_producer);
    }
#if defined(NVDS_OBJ_ENCODE_AVAILABLE)
    if (ctx.encoder_ctx) {
        nvds_obj_enc_destroy_context(ctx.encoder_ctx);
    }
#endif

    return 0;
}
