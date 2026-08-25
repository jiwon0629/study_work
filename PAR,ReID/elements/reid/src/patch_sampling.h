#pragma once

#include <cstdint>

namespace mantis::elements::reid {

bool should_sample_interval_or_throw(int interval_ms, int64_t elapsed_ms);

} // namespace mantis::elements::reid
