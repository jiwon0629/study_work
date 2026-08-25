#pragma once

#include <string>

namespace mantis::elements::reid {

void validate_kafka_sink_or_throw(bool enabled, const std::string& bootstrap_servers, const std::string& topic);

} // namespace mantis::elements::reid
