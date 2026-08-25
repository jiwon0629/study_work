#!/bin/bash

INPUT_DIR="$1"

if [ -z "$INPUT_DIR" ]; then
  echo "사용법: $0 <입력 경로>"
  exit 1
fi

if [ ! -d "$INPUT_DIR" ]; then
  echo "유효한 입력 경로를 입력하세요."
  exit 1
fi

for DIR in "$INPUT_DIR"/*; do
  if [ -d "$DIR" ]; then
    if [[ "$(basename "$DIR")" == *"Segmentation"* ]]; then
      echo "삭제 중: $DIR"
      rm -rf "$DIR"
    fi
  fi
done

echo "모든 'Segmentation' 폴더를 삭제했습니다."

