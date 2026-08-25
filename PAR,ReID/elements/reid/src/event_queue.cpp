#include "event_queue.h"

#include "error.h"

namespace mantis::elements::reid {

void validate_queue_size_or_throw(size_t size) {
    if (size == 0) {
        mantis::fail("CONFIG_SCHEMA", "async_queue_size must be > 0");
    }
}

} // namespace mantis::elements::reid
