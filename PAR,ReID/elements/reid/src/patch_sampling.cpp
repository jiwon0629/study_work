#include "patch_sampling.h"

#include "error.h"

namespace mantis::elements::reid {

bool should_sample_interval_or_throw(int interval_ms, int64_t elapsed_ms) {
    if (interval_ms < 0) {
        mantis::fail("CONFIG_SCHEMA", "sampling interval must be >= 0");
    }
    if (interval_ms == 0) {
        return true;
    }
    return elapsed_ms >= interval_ms;
}

} // namespace mantis::elements::reid
