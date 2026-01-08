import base64
from typing import List

class ImageProcessor:
    @staticmethod
    def bytes_to_base64(raw_bytes: bytes) -> str:
        """Converts raw bytes to a string for JSON/DB storage."""
        return base64.b64encode(raw_bytes).decode('utf-8')

    @staticmethod
    def base64_to_bytes(b64_string: str) -> bytes:
        """Converts stored string back to raw bytes for processing."""
        return base64.b64decode(b64_string)

    @staticmethod
    def pack_images(image_byte_list: List[bytes]) -> List[str]:
        """Takes a list of raw images and prepares them for storage."""
        return [ImageProcessor.bytes_to_base64(img) for img in image_byte_list]