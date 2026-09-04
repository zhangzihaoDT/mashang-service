from typing import Optional
from capabilities.ocr.schemas import OcrResult, OcrRequest


class BaseOcrProvider:
    name: str = "base"

    def process(self, request: OcrRequest, image_bytes: bytes) -> OcrResult:
        raise NotImplementedError


def get_provider(name: str) -> BaseOcrProvider:
    if name == "volcengine":
        from capabilities.ocr.providers.volcengine_ocr_provider import VolcengineOcrProvider
        return VolcengineOcrProvider()
    elif name == "mock":
        from capabilities.ocr.providers.mock_provider import MockOcrProvider
        return MockOcrProvider()
    else:
        raise ValueError(f"Unknown provider: {name}")
