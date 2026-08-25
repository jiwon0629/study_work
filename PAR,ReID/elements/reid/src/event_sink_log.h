#pragma once

#include <string>

namespace mantis::elements::reid {

void validate_log_sink_or_throw(const std::string& stream_id, const std::string& element_type);

} // namespace mantis::elements::reid
