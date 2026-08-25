#pragma once

#include <string>

namespace mantis::elements::reid {

struct ReidCli {
    std::string config_file;
    bool validate_only = false;
};

ReidCli parse_reid_cli_or_throw(int argc, char** argv);

} // namespace mantis::elements::reid
