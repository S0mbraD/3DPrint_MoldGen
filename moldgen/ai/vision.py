"""多模态视觉理解 — Qwen-VL (通义千问视觉)

用于:
  - 分析 3D 模型截图识别解剖结构
  - 审查 AI 生成模型的质量
  - 辅助支撑板位置建议
"""

from __future__ import annotations

import base64
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class VisionAnalyzer:
    """多模态视觉分析器 — Qwen-VL"""

    _instance: VisionAnalyzer | None = None

    def __new__(cls) -> VisionAnalyzer:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if hasattr(self, "_initialized"):
            return
        self._initialized = True

    async def analyze_image(
        self,
        image_path: str,
        question: str,
        model: str = "qwen-vl",
        detail: str = "auto",
    ) -> dict:
        """分析单张图片"""
        from moldgen.ai.service_manager import AIServiceManager
        svc = AIServiceManager()

        image_b64 = self._encode_image(image_path)
        if not image_b64:
            return {"success": False, "error": "图片读取失败"}

        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{image_b64}",
                            "detail": detail,
                        },
                    },
                    {"type": "text", "text": question},
                ],
            }
        ]

        try:
            result = await svc.chat_completion(messages=messages, model=model, max_tokens=2048)
            if result:
                return {
                    "success": True,
                    "analysis": result["content"],
                    "model": result.get("model", model),
                    "usage": result.get("usage"),
                }
            return {"success": False, "error": "无响应"}
        except Exception as e:
            logger.error("Vision analysis failed: %s", e)
            return {"success": False, "error": str(e)}

    async def review_generated_model(self, screenshot_path: str) -> dict:
        """审查 AI 生成的 3D 模型质量"""
        question = (
            "请分析这个 3D 医学器官模型的质量:\n"
            "1. 解剖结构是否准确? 能识别出哪些解剖部位?\n"
            "2. 网格表面质量如何? 是否光滑、有无明显瑕疵?\n"
            "3. 几何拓扑是否适合硅胶铸造模具制作?\n"
            "4. 总体评分 (1-10) 和改进建议。\n"
            "请用中文回答。"
        )
        return await self.analyze_image(screenshot_path, question)

    async def suggest_insert_positions(self, screenshot_path: str, organ_type: str) -> dict:
        """根据模型截图建议支撑板位置"""
        question = (
            f"这是一个 {organ_type} 的 3D 模型。请分析:\n"
            "1. 模型的主要解剖结构和空间分布\n"
            "2. 建议在哪些位置放置内嵌支撑板 (用于硅胶模具铸造)\n"
            "3. 推荐的支撑板方向 (横断面/矢状面/冠状面)\n"
            "4. 需要注意的脆弱区域或空腔结构\n"
            "请用中文回答，给出具体的位置建议。"
        )
        return await self.analyze_image(screenshot_path, question)

    async def compare_models(self, image1_path: str, image2_path: str, context: str = "") -> dict:
        """对比两个模型截图"""
        from moldgen.ai.service_manager import AIServiceManager
        svc = AIServiceManager()

        b64_1 = self._encode_image(image1_path)
        b64_2 = self._encode_image(image2_path)
        if not b64_1 or not b64_2:
            return {"success": False, "error": "图片读取失败"}

        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64_1}"}},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64_2}"}},
                    {
                        "type": "text",
                        "text": f"请对比这两个 3D 模型的差异。{context}\n"
                                "哪个质量更好? 各自有什么优缺点? 请用中文回答。",
                    },
                ],
            }
        ]

        try:
            result = await svc.chat_completion(messages=messages, model="qwen-vl", max_tokens=2048)
            if result:
                return {"success": True, "comparison": result["content"]}
            return {"success": False, "error": "无响应"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    @staticmethod
    def _encode_image(path: str) -> str:
        try:
            data = Path(path).read_bytes()
            return base64.b64encode(data).decode()
        except Exception:
            return ""
