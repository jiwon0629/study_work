#include "patch_encoder.h"

#include "error.h"

namespace mantis::elements::reid {

void validate_patch_jpeg_quality_or_throw(int quality) {
    if (quality <= 0 || quality > 100) {
        mantis::fail("CONFIG_SCHEMA", "patch_jpeg_quality must be between 1 and 100");
    }
}

void validate_patch_message_size_or_throw(size_t max_bytes) {
    if (max_bytes == 0) {
        mantis::fail("CONFIG_SCHEMA", "patch_message_max_bytes must be > 0");
    }
}

} // namespace mantis::elements::reid
