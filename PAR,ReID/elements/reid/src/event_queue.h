#pragma once

#include <string>

namespace mantis::elements::reid {

struct EventRecord {
    std::string key;
    std::string payload;
};

void validate_queue_size_or_throw(size_t size);

} // namespace mantis::elements::reid
