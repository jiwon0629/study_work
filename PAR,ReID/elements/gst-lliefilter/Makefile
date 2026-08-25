# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary
#
# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

WITH_OPENCV?=0

CUDA_VER?=
ifeq ($(CUDA_VER),)
  $(error "CUDA_VER is not set")
endif

CXX:= g++
NVCC:= /usr/local/cuda-$(CUDA_VER)/bin/nvcc

SRCS:= gstlliefilter.cpp
CU_SRCS:= trt_filter_preprocess.cu trt_filter_postprocess.cu
INCS:= $(wildcard *.h)
LIB:=libnvdsgst_lliefilter.so

NVDS_VERSION:=8.0
NVDS_PATH?=/opt/nvidia/deepstream/deepstream-$(NVDS_VERSION)

CFLAGS+= -fPIC -std=c++14 -DDS_VERSION=\"8.0.0\" \
	-I /usr/local/cuda-$(CUDA_VER)/include \
	-I $(NVDS_PATH)/sources/includes \
	-I ../../includes

NVCCFLAGS+= -Xcompiler -fPIC -std=c++14 \
	-I /usr/local/cuda-$(CUDA_VER)/include \
	-I $(NVDS_PATH)/sources/includes \
	-I ../../includes

GST_INSTALL_DIR?=/opt/nvidia/deepstream/deepstream-$(NVDS_VERSION)/lib/gst-plugins/
LIB_INSTALL_DIR?=/opt/nvidia/deepstream/deepstream-$(NVDS_VERSION)/lib/

LIBS := -shared -Wl,-no-undefined \
	-L/usr/local/cuda-$(CUDA_VER)/lib64/ -lcudart -ldl \
	-L$(LIB_INSTALL_DIR) -lnvdsgst_helper -lnvdsgst_meta -lnvds_meta -lnvbufsurface -lnvbufsurftransform \
	-L/usr/lib/x86_64-linux-gnu -lnvinfer -lnvinfer_plugin \
	-Wl,-rpath,$(LIB_INSTALL_DIR) -Wl,-rpath,/usr/lib/x86_64-linux-gnu

PKGS:= gstreamer-1.0 gstreamer-base-1.0 gstreamer-video-1.0

CFLAGS+=$(shell pkg-config --cflags $(PKGS))
LIBS+=$(shell pkg-config --libs $(PKGS))

OBJS:= $(SRCS:.cpp=.o) $(CU_SRCS:.cu=.o)

all: $(LIB)

%.o: %.cpp $(INCS) Makefile
	@echo $(CFLAGS)
	$(CXX) -c -o $@ $(CFLAGS) $<

%.o: %.cu Makefile
	@echo $(NVCCFLAGS)
	$(NVCC) -c -o $@ $(NVCCFLAGS) $<

$(LIB): $(OBJS) Makefile
	@echo $(CFLAGS)
	$(CXX) -o $@ $(OBJS) $(LIBS)

install: $(LIB)
	cp -rv $(LIB) $(GST_INSTALL_DIR)

clean:
	rm -rf $(OBJS) $(LIB)
