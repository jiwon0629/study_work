#include "reid_pipeline_builder.h"

#include "error.h"

namespace mantis::elements::reid {

void validate_pipeline_source_or_throw(const std::string& input_url) {
    if (input_url.empty()) {
        mantis::fail("CONFIG_SCHEMA", "input_url is required");
    }
}

} // namespace mantis::elements::reid
