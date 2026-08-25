import tensorrt as trt
import cupy as cp
import numpy as np
import os

class RTDETR_TRT_Model:
    def __init__(self, gpu, model_path, input_shape, datatype=np.float32, logger=None):
        self.gpu = gpu
        try:
            with cp.cuda.Device(self.gpu).use():
                # Set TensorRT logger level to ERROR to suppress warnings
                self.TRT_LOGGER = trt.Logger(trt.Logger.ERROR)
                self.engine = self.load_engine(model_path)
                self.context = self.engine.create_execution_context()
                self.inputs, self.outputs = self.allocate_buffers()
        except cp.cuda.runtime.CUDARuntimeError as e:
            max_gpu = cp.cuda.runtime.getDeviceCount()
            if logger:
                logger.error(f"RT_DETR_CP | Select gpu: {gpu} exceeds the maximum number of GPUs, Num GPUs: {max_gpu}")
            assert False, f"RT_DETR_CP | Select gpu: {gpu} exceeds the maximum number of GPUs, Num GPUs: {max_gpu}"

    def allocate_buffers(self):
        inputs = {}
        outputs = {}
        with cp.cuda.Device(self.gpu).use():
            for binding in range(self.engine.num_bindings):
                tensor_name = self.engine.get_tensor_name(binding)
                dtype = trt.nptype(self.engine.get_tensor_dtype(tensor_name))
                dims = self.engine.get_tensor_shape(tensor_name)
                shape = tuple(dims[i] for i in range(len(dims)))
                host_mem = cp.empty(shape, dtype)
                device_mem = cp.empty(shape, dtype)

                if self.engine.binding_is_input(binding):
                    inputs[tensor_name] = (host_mem, device_mem)
                else:
                    outputs[tensor_name] = (host_mem, device_mem)
        return inputs, outputs

    def predict(self, inputs):
        results = []
        with cp.cuda.Device(self.gpu).use():
            for input_name, data in inputs.items():
                if input_name in self.inputs:
                    host_mem, device_mem = self.inputs[input_name]
                    data_cp = cp.asarray(data)
                    host_mem[:] = data_cp
                    device_mem[:] = host_mem

            input_buffers = [buf[1].data.ptr for buf in self.inputs.values()]
            output_buffers = [buf[1].data.ptr for buf in self.outputs.values()]
            self.context.execute_v2(input_buffers + output_buffers)

            for binding in range(self.engine.num_bindings):
                if not self.engine.binding_is_input(binding):
                    tensor_name = self.engine.get_tensor_name(binding)
                    host_mem, device_mem = self.outputs[tensor_name]
                    host_mem[:] = device_mem
                    results.append(host_mem.copy())

            for idx in range(len(results)):
                results[idx] = results[idx].get().astype(np.float32)
                if len(results) > 1:
                    results[1] = results[1].reshape(900, 6)
                if len(results) > 0:
                    results[0] = results[0].astype(np.int8)
        return results

    def load_engine(self, engine_file_path):
        if not os.path.exists(engine_file_path):
            raise FileNotFoundError(f"Engine Error | Model path not found: {engine_file_path}")
        with open(engine_file_path, "rb") as f, trt.Runtime(self.TRT_LOGGER) as runtime:
            engine = runtime.deserialize_cuda_engine(f.read())
            if engine is None:
                raise Exception("Failed to deserialize the TensorRT engine.")
            return engine
