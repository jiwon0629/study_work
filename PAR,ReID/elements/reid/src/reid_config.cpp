#include "reid_config.h"

#include "strict_config.h"

namespace mantis::elements::reid {

ReidCli parse_reid_cli_or_throw(int argc, char** argv) {
    const auto cli = mantis::parse_cli_or_throw(argc, argv);
    return ReidCli{.config_file = cli.config_file, .validate_only = cli.validate_only};
}

} // namespace mantis::elements::reid
