import os
import shutil

def create_folders_and_copy_images(label_dir, image_dir, source_image_dir):
    for root, dirs, files in os.walk(label_dir):
        relative_folder_path = os.path.relpath(root, label_dir)
        
        target_folder_path = os.path.join(image_dir, relative_folder_path)
        if not os.path.exists(target_folder_path):
            os.makedirs(target_folder_path)
            print(f"Created folder: {target_folder_path}")
        
        for file in files:
            if file.endswith('.json'):
                json_filename = os.path.splitext(file)[0]
                image_filename = f"{json_filename}.jpg"
                
                for img_root, img_dirs, img_files in os.walk(source_image_dir):
                    if image_filename in img_files:
                        source_image_path = os.path.join(img_root, image_filename)
                        target_image_path = os.path.join(target_folder_path, image_filename)
                        shutil.copy(source_image_path, target_image_path)
                        print(f"Copied {source_image_path} to {target_image_path}")
                        break
                else:
                    print(f"Image file {image_filename} not found for JSON {file}")

if __name__ == "__main__":
    label_dir = "/ai-video-converter/datasets/sample_Data/label"
    image_dir = "/ai-video-converter/datasets/sample_Data/image"
    source_image_dir = "/volume/028.저조도_환경_데이터/sample_Data/"
    
    create_folders_and_copy_images(label_dir, image_dir, source_image_dir)
    print("Folder creation and image copying process completed.")
