import tensorrt as trt

def check_engine(engine_path):
    logger = trt.Logger(trt.Logger.INFO)
    with open(engine_path, 'rb') as f:
        runtime = trt.Runtime(logger)
        engine = runtime.deserialize_cuda_engine(f.read())
        
        print(f"Engine: {engine_path}")
        # For newer TRT versions, we iterate over tensor names
        for i in range(engine.num_io_tensors):
            name = engine.get_tensor_name(i)
            mode = engine.get_tensor_mode(name)
            shape = engine.get_tensor_shape(name)
            dtype = engine.get_tensor_dtype(name)
            print(f"Tensor {i}: name={name}, mode={mode}, shape={shape}, dtype={dtype}")

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        check_engine(sys.argv[1])
    else:
        print("Please provide engine path")
