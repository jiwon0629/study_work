# 핵심 목적: NVIDIA TensorRT 엔진을 사용하여 추론 속도를 극대화하고, PyCUDA를 통해 GPU 메모리(VRAM)를 직접 제어함으로써 CPU-GPU 간 데이터 전송 오버헤드를 줄이는 것입니다.
# 이 파일은 .trt 엔진 파일을 로드하고, GPU 메모리 버퍼를 할당하며, 데이터를 GPU로 전송/수신하는 저수준(Low-level) 하드웨어 제어를 담당합니다.
import tensorrt as trt # NVIDIA TensorRT 라이브러리: 모델 최적화 및 추론 가속을 위해 사용합니다.
import os
import numpy as np
import pycuda.driver as cuda # GPU 메모리 할당 및 데이터 전송(memcpy)을 위해 사용합니다.
import pycuda.autoinit # CUDA 컨텍스트를 자동으로 초기화하여 설정 과정을 단순화합니다.
import traceback

class NOX_TRT_Model:
    """
    TensorRT 기반의 NOX 모델 래퍼 클래스입니다.
    엔진 로드 -> 메모리 할당 -> 추론(Predict) 순으로 동작합니다.
    """
    def __init__(self, gpu, model_path, input_shape, datatype=np.float32, logger=None):
        # [GPU 장치 설정] 사용할 GPU 번호를 지정하고 CUDA 컨텍스트를 생성합니다.
        try:
            cuda.init()
            self.device = cuda.Device(gpu)
            self.ctx = self.device.make_context() # 현재 스레드에 GPU 컨텍스트를 바인딩합니다.
        except pycuda._driver.LogicError:
            # 지정한 GPU 번호가 시스템의 실제 GPU 개수보다 많을 경우 에러를 발생시킵니다.
            max_gpu = cuda.Device.count()
            if logger is not None:
                logger.Error(f"Select gpu: {gpu} exceeds the maximum number of GPUs, Num GPUs : {max_gpu}")
            assert False, f"Select gpu: {gpu} exceeds the maximum number of GPUs, Num GPUs : {max_gpu}"
        except pycuda._driver.MemoryError:
            # GPU 메모리가 부족하여 모델을 올릴 수 없는 경우를 처리합니다.
            if logger is not None:
                logger.error(f"GPU memory is full : GPU{gpu}")
                logger.error(f"=================== Program shutdown =====================")
            else:
                print(f"GPU memory is full : GPU{gpu}")
        except Exception as e:
            if logger is not None:
                logger.error("MODEL_LOOPER | Exception occurred", exc_info=True)
                logger.error(traceback.format_exc())
            else:
                print("MODEL_LOOPER | Exception occurred")
            
        # TensorRT 로그 레벨을 ERROR로 설정하여 불필요한 디버그 메시지를 숨깁니다.
        self.TRT_LOGGER = trt.Logger(trt.Logger.ERROR)
        # 모델 입력 크기에 맞는 빈 numpy 배열을 생성하여 메모리 크기 계산용으로 사용합니다.
        self.datatype = np.empty(input_shape, dtype=datatype)
        # .trt 파일을 읽어 TensorRT 엔진 객체로 역직렬화(Deserialize)합니다.
        engine = self.load_engine(model_path)
        # 추론에 필요한 GPU 메모리를 미리 할당합니다.
        self.memory_alloc(engine)

    def __del__(self):
        # 객체가 소멸될 때 GPU 컨텍스트를 해제하여 메모리 누수를 방지합니다.
        self.release()

    def release(self):
        if hasattr(self, 'ctx') and self.ctx:
            self.ctx.pop() # CUDA 컨텍스트 스택에서 현재 컨텍스트를 제거합니다.
            del self.ctx

    def memory_alloc(self, engine):
        """
        추론 시 데이터를 주고받을 GPU 메모리 버퍼를 할당하는 함수입니다.
        """
        # 엔진으로부터 실행 컨텍스트를 생성합니다. (추론의 실제 실행 단위)
        self.context = engine.create_execution_context()
        # 입력 텐서의 이름을 'input'으로 지정하고 셰이프를 설정합니다.
        self.context.set_input_shape('input', self.datatype.shape) 
        # 출력 데이터를 저장할 빈 numpy 배열을 생성합니다.
        self.output = np.empty(self.datatype.shape, dtype=self.datatype.dtype)
        
        # [중요] Host(CPU) 메모리가 아닌 Device(GPU) 메모리를 할당합니다.
        # memcpy_htod_async 등에서 사용할 주소값을 확보하는 과정입니다.
        self.d_input = cuda.mem_alloc(1 * self.datatype.nbytes)
        self.d_output = cuda.mem_alloc(1 * self.output.nbytes)

        # TensorRT가 데이터를 읽고 쓸 메모리 주소 리스트(Bindings)를 생성합니다.
        self.bindings = [int(self.d_input), int(self.d_output)]
        # 비동기 실행을 위한 CUDA 스트림을 생성합니다. (병렬 처리 가능)
        self.stream = cuda.Stream()

    def predict(self, batch):
        """
        실제 추론을 수행하는 핵심 함수입니다.
        """
        self.ctx.push() # GPU 컨텍스트 활성화
        try:
            # [Step 1: CPU -> GPU] 입력 데이터를 GPU 메모리(d_input)로 비동기 복사합니다.
            cuda.memcpy_htod_async(self.d_input, batch, self.stream)
            # [Step 2: 추론 실행] GPU 내에서 TensorRT 엔진을 통해 연산을 수행합니다.
            self.context.execute_async_v2(bindings=self.bindings, stream_handle=self.stream.handle)
            # [Step 3: GPU -> CPU] 연산 결과(d_output)를 다시 CPU 메모리(self.output)로 복사합니다.
            cuda.memcpy_dtoh_async(self.output, self.d_output, self.stream)
            # [Step 4: 동기화] 비동기 작업이 모두 완료될 때까지 기다립니다.
            self.stream.synchronize()
        finally:
            self.ctx.pop() # GPU 컨텍스트 해제

        return self.output

    def load_engine(self, engine_file_path, verbose=False):
        """
        저장된 .trt 바이너리 파일을 읽어 TensorRT 엔진 객체로 변환합니다.
        """
        assert os.path.exists(engine_file_path)
        if verbose: print("Reading engine from file {}".format(engine_file_path))
        # Runtime 객체를 통해 파일 내용을 CUDA 엔진으로 역직렬화합니다.
        with open(engine_file_path, "rb") as f, trt.Runtime(self.TRT_LOGGER) as runtime:
            return runtime.deserialize_cuda_engine(f.read())

# 1. pycuda 사용 이유: TensorRT는 연산만 수행할 뿐, 데이터를 GPU로 옮기는 것은 사용자의 몫입니다. pycuda를 통해 메모리를 직접 할당(mem_alloc)하고 전송(memcpy)함으로써 최대의 효율을 냅니다.
# 2. async 함수 사용 이유: memcpy_htod_async와 execute_async_v2를 사용하여 데이터 전송과 연산을 겹치게(Overlap) 처리함으로써 GPU 유휴 시간을 줄입니다.
# 3. stream.synchronize() 이유: 비동기 작업은 결과가 나오기 전에 다음 코드가 실행될 수 있습니다. 정확한 결과값을 받기 위해 모든 작업이 끝날 때까지 대기하는 지점을 만들어준 것입니다.