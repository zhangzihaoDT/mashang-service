from ocr.schemas import OcrRequest, OcrResult, OcrBlock, OcrQuality
from ocr.providers import BaseOcrProvider


class MockOcrProvider(BaseOcrProvider):
    name = "mock"

    def process(self, request: OcrRequest, image_bytes: bytes) -> OcrResult:
        return OcrResult(
            source_image_path=request.source_image_path,
            provider="mock",
            mode=request.mode,
            status="success",
            raw_text="Mock OCR result: 产品商标 长城 产品型号 CC1030QA00A 企业名称 长城汽车股份有限公司",
            markdown="# Mock OCR\n\n- 产品商标: 长城\n- 产品型号: CC1030QA00A\n- 企业名称: 长城汽车股份有限公司",
            blocks=[
                OcrBlock(text="产品商标 长城", confidence=0.95, line_num=1),
                OcrBlock(text="产品型号 CC1030QA00A", confidence=0.95, line_num=2),
                OcrBlock(text="企业名称 长城汽车股份有限公司", confidence=0.95, line_num=3),
            ],
            image_sha256="",
            ocr_result_id="mock_result_id",
            created_at="",
            quality=OcrQuality(mean_confidence=0.95, low_confidence_blocks=0, needs_manual_review=False),
            error=None,
        )
