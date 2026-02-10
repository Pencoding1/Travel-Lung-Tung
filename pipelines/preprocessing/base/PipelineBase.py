import logging

from concurrent.futures import ProcessPoolExecutor, as_completed, Future, wait, FIRST_COMPLETED


from config.preprocessing_config import PreprocessConfig
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Tuple, Generator, Optional, Type

from pathlib import Path

class BasePreprocessor(ABC):

    def __init__(self, config:Optional[PreprocessConfig]=None, files_dir: Optional[str]="./data/") -> None:
        self.config = config if config else PreprocessConfig()
        if files_dir:
            self.path = Path(files_dir)
            if not self.path.exists():
                 raise FileNotFoundError(f"Path not found: {files_dir}")
            if not self.path.is_dir():
                raise NotADirectoryError(f"Path is not a directory: {files_dir}")
        else:
            self.path = None

    @abstractmethod        
    def filter(self, md_text:str) -> str:...

    @abstractmethod
    def clean(self, md_text:str) -> str:...
    
    def save_results(self, result:List) -> None:...

    def get_metadata(self, file_path: Path) -> Tuple[str, str]:
        parts = {p.lower() for p in file_path.parts}
        
        found_agency = list(parts.intersection(self.config.AGENCIES))
        found_city = list(parts.intersection(self.config.CITIES))
        
        agency = found_agency[0] if found_agency else "unknown_agency"
        city = found_city[0] if found_city else "unknown_city"
        
        return agency, city

    def _load_all_generator(self) -> Generator[Dict[str, Any], None, None]:
        if self.path:
            for file_path in self.path.rglob(self.config.PATTERN):
                agency, city = self.get_metadata(file_path)
                filename = file_path.name
                yield {
                    "agency": agency,
                    "city": city,
                    "filename": filename,
                    "path": str(file_path),
                    "results": None 
                }
        else:
            raise ValueError("Path is not found.")
        
    @staticmethod
    def _process_worker(file_info: Dict[str, Any], cls_type: Type['BasePreprocessor'], config: PreprocessConfig) -> Dict[str, Any]:
        try:
            processor_instance = cls_type(config=config, files_dir=None)
            file_path = Path(file_info['path'])
            text = file_path.read_text(encoding='utf-8')

            cleaned_content = processor_instance.clean(text)
            final_content = processor_instance.filter(cleaned_content)

            file_info['results'] = final_content
            return file_info
        
        except Exception as e:
            logging.error(f"Error processing file {file_info['filename']}: {e}")
            file_info['results'] = None
            file_info['error'] = str(e)
            return file_info

    def transform(self) -> Generator:
        current_class = self.__class__
        current_config = self.config
        
        try:
            with ProcessPoolExecutor(max_workers=self.config.NUM_WORKERS) as executor:
                pending_futures: List[Future] = []
                input_generator = self._load_all_generator()
                
                def submit_next():
                    try:
                        file_info = next(input_generator)
                        future = executor.submit(
                                                    BasePreprocessor._process_worker, 
                                                    file_info,                        
                                                    current_class,                    
                                                    current_config                    
                                                )
                        pending_futures.append(future)
                        return True
                    except StopIteration:
                        return False

                for _ in range(self.config.BATCH_SIZE):
                    if not submit_next():
                        break
                
                while pending_futures:
                    done, not_done = wait(pending_futures, return_when=FIRST_COMPLETED)
                    pending_futures = list(not_done)

                    for future in done:
                        try:
                            yield future.result(timeout=100)
                        except Exception as e:
                            logging.error(f"Worker crashed: {e}")
                        
                        submit_next()
                        
        except Exception as e:
            logging.error(f"Critical error during transformation: {e}", exc_info=True)




class BaseExtractor(ABC):...
    
