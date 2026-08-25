#pragma once

#include <cstddef>

namespace mantis::elements::reid {

void validate_patch_jpeg_quality_or_throw(int quality);
void validate_patch_message_size_or_throw(size_t max_bytes);

} // namespace mantis::elements::reid
