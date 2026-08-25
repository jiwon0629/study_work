import argparse
import os
import multiprocessing as mp
from pathlib import Path
from utils import gs_print_program_limitations, argparse_type_bool, custom_error, ConfigManager
from process import image_process, video_process

class NOX_converter():
    def __init__(self,
                 input_dir,
                 result_dir,
                 nox_apply=True,
                 rtdetr_apply=False,
                 mAP_path=None,
                 mAP=False,
                 save_csv=False,
                 config_path="/ai-video-converter/src/config.ini",
                 concat_apply=False,
                 ):
        self.input_dir = Path(input_dir)
        self.result_dir = Path(result_dir)
        self.nox_apply = nox_apply
        self.rtdetr_apply = rtdetr_apply
        self.mAP_path = Path(mAP_path) if mAP_path else None
        self.mAP = mAP
        self.concat_apply = concat_apply
        config = ConfigManager(config_path)
        self.ini_dict = config.get_config_dict()
        # main.py uses the default CONFIG JSON_PATH
        self.save_csv = self.ini_dict['CONFIG']['PROCESS_TIME_CSV_PATH'] if save_csv else None
        
        mp.set_start_method('spawn')
        self.mAP_List = []  

    def process_run(self):
        gs_print_program_limitations(self.input_dir, self.result_dir)
        file_list, success = custom_error(
            self.input_dir,
            self.result_dir,
            self.nox_apply,
            self.rtdetr_apply,
            self.mAP,
            self.ini_dict,
            self.concat_apply,
            )
        if not success:
            return

        image_files = [f for f in file_list if f.is_file() and f.suffix.lower() in ['.jpg', '.jpeg', '.png']]
        total_files = len(image_files)
        
        for idx, input_path in enumerate(image_files, start=1):
            if input_path.is_file():
                image_process(
                    self.ini_dict,
                    input_path, 
                    self.input_dir,
                    self.result_dir,
                    self.nox_apply,
                    self.rtdetr_apply,
                    self.save_csv,
                    self.mAP,
                    self.mAP_path,
                    self.mAP_List,
                )
                print(f"Processed {idx}/{total_files} images processed successfully")
                
        for input_path in file_list:
            if input_path.suffix.lower() in ['.mp4', '.avi', '.mov', '.mkv', '.webm', '.wmv', '.flv']:
                video_process(
                    self.ini_dict,
                    input_path,
                    self.input_dir, 
                    self.result_dir,
                    self.nox_apply,
                    self.rtdetr_apply,
                    self.save_csv,
                    self.concat_apply,
                )
                print(f"{input_path} video process finish")

        print("Processed successfully")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input_dir", default="./inputs", type=str)
    parser.add_argument("--result_dir", default="./outputs", type=str)
    parser.add_argument("--nox", type=argparse_type_bool, default=True)
    parser.add_argument("--rtdetr", type=argparse_type_bool, default=False)
    parser.add_argument("--mAP", default=None, type=str)
    parser.add_argument("--save_csv", type=argparse_type_bool, default=False)
    parser.add_argument("--config_path", default="/ai-video-converter/src/config.ini", type=str)
    parser.add_argument("--concat_apply", type=argparse_type_bool, default=False)
    args = parser.parse_args()

    mAP = True if args.mAP else False

    v_loader = NOX_converter(
        input_dir=args.input_dir,
        result_dir=args.result_dir,
        nox_apply=args.nox,
        rtdetr_apply=args.rtdetr,
        mAP_path=args.mAP,
        mAP=mAP,
        save_csv=args.save_csv,
        config_path=args.config_path,
        concat_apply=args.concat_apply,
    )
    v_loader.process_run()
