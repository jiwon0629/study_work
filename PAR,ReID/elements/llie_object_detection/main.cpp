#include "../object_detection/src/detection_app.h"

int main(int argc, char** argv) {
    return mantis::elements::object_detection::run_detection_app(
        argc,
        argv,
        mantis::elements::object_detection::PipelineVariant::kLlieObjectDetection);
}
