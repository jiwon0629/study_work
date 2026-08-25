import configparser
 
class ConfigManager:
    def __init__(self, config_file_path):
        self.config = configparser.ConfigParser()
        self.config.optionxform = str  
        self.config_file_path = config_file_path
        self.config.read(config_file_path)
        
        self.type_map = {
            'CONFIG': {
                'NOX_MODEL_PATH': str,
                'PROCESS_TIME_CSV_PATH' : str,
                'GPU': int,
                'BATCH' : int,
                'CHANNEL' : int,
            },
            'NOX': {
                'NOX_MODEL_PATH': str,
                'NOX_MODEL_MAX_WIDTH': int,
                'NOX_MODEL_MAX_HEIGHT' : int,
                'NOX_MODEL_MIN_WIDTH': int,
                'NOX_MODEL_MIN_HEIGHT' : int,
            },
            'RTDETR': {
                'RTDETR_MODEL_PATH': str,
                'CONFIG_PATH' : str,
                'RTDETR_MODEL_WIDTH' : int,
                'RTDETR_MODEL_HEIGHT' : int,
            },
            'YOLO': {
                'YOLO_MODEL_PATH': str,
                'YOLO_CONF': float,
                'YOLO_IOU': float,
            },
        }
        
    def get_config_dict(self):
        all_config_dict = {}
            
        for section in self.config.sections():
            # print(f"Processing section: {section}")
            section_dict = {}
            
            if section not in self.type_map:
                # print(f"Warning: Section {section} is not in type_map")
                continue
            
            for key, value in self.config[section].items():
                if key in self.type_map[section]:
                    value_type = self.type_map[section][key]
                    section_dict[key] = value_type(value)
                else:
                    section_dict[key] = value
            
            all_config_dict[section] = section_dict
            
        return all_config_dict

