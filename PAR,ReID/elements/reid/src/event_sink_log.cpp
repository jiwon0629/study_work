#include "event_sink_log.h"

#include "error.h"

namespace mantis::elements::reid {

void validate_log_sink_or_throw(const std::string& stream_id, const std::string& element_type) {
    if (stream_id.empty()) {
        mantis::fail("CONFIG_SCHEMA", "stream_id is required for log sink");
    }
    if (element_type.empty()) {
        mantis::fail("CONFIG_SCHEMA", "type is required for log sink");
    }
}

} // namespace mantis::elements::reid
