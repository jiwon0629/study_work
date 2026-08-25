#!/bin/bash

SOURCE_DIR="$1"
DEST_DIR="$2"

if [ -z "$SOURCE_DIR" ] || [ -z "$DEST_DIR" ]; then
  echo "사용법: $0 <ZIP 파일 폴더 경로> <압축 해제할 폴더 경로>"
  exit 1
fi

if [ ! -d "$SOURCE_DIR" ]; then
  echo "유효한 ZIP 파일 폴더 경로를 입력하세요."
  exit 1
fi

mkdir -p "$DEST_DIR"

ZIP_FILES=$(find "$SOURCE_DIR" -maxdepth 1 -type f -name '*.zip')

if [ -z "$ZIP_FILES" ]; then
  echo "폴더에 zip 파일이 없습니다."
  exit 0
fi

for ZIP_FILE in $ZIP_FILES; do
  BASE_NAME=$(basename "$ZIP_FILE" .zip)
  FOLDER_NAME="$DEST_DIR/$BASE_NAME"
  mkdir -p "$FOLDER_NAME"
  
  echo "압축 해제 중: $ZIP_FILE -> $FOLDER_NAME"
  unzip -o "$ZIP_FILE" -d "$FOLDER_NAME"
done

echo "모든 zip 파일의 압축을 해제했습니다."

