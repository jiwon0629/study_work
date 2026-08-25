#!/bin/bash

INPUT_DIR="$1"
OUTPUT_DIR="$2"

if [ -z "$INPUT_DIR" ] || [ -z "$OUTPUT_DIR" ]; then
  echo "사용법: $0 <입력 경로> <출력 경로>"
  exit 1
fi

if [ ! -d "$INPUT_DIR" ]; then
  echo "유효한 입력 경로를 입력하세요."
  exit 1
fi

mkdir -p "$OUTPUT_DIR"

for DIR in "$INPUT_DIR"/*; do
  if [ -d "$DIR" ]; then
    FOLDER_NAME=$(basename "$DIR")
    mkdir -p "$OUTPUT_DIR/$FOLDER_NAME"
    
    IMAGE_FILES=$(find "$DIR" -maxdepth 1 -type f | head -n 100)
    for FILE in $IMAGE_FILES; do
      cp "$FILE" "$OUTPUT_DIR/$FOLDER_NAME/"
    done
  fi
done

echo "모든 이미지 파일을 복사했습니다."

