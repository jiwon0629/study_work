#!/bin/bash

IMAGE_NAME="hub.inbic.duckdns.org/ai_dev/ai-video-converter"
TAG="0.2"

docker build --no-cache -t ${IMAGE_NAME}:${TAG} .
