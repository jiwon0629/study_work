#pragma once

#include <string>

namespace mantis::elements::reid {

std::string build_tracking_key(const std::string& stream_id, const std::string& tracking_id);

} // namespace mantis::elements::reid
