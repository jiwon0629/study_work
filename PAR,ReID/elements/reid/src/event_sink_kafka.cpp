#include "event_sink_kafka.h"

#include "error.h"

namespace mantis::elements::reid {

void validate_kafka_sink_or_throw(bool enabled, const std::string& bootstrap_servers, const std::string& topic) {
    if (!enabled) {
        return;
    }
    if (bootstrap_servers.empty()) {
        mantis::fail("CONFIG_SCHEMA", "kafka.bootstrap_servers is required when kafka is enabled");
    }
    if (topic.empty()) {
        mantis::fail("CONFIG_SCHEMA", "kafka.topic is required when kafka is enabled");
    }
}

} // namespace mantis::elements::reid
