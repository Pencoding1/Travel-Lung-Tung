from base.PipelineBase import BasePreprocessor

class VietnamTravelPreprocessor(BasePreprocessor):...

class VietravelPreprocessor(BasePreprocessor):...

class VNTravelPreprocessor(BasePreprocessor):...

class TravelokaPreprocessor(BasePreprocessor):
    def __init__(self):
        super().__init__()

    def filter(self, text: str) -> str:
        return ""

    def clean(self, text: str) -> str:
        return ""
