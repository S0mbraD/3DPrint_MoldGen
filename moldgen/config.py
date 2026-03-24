"""应用配置 — 通过环境变量或 .env 文件加载"""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings


class GPUConfig(BaseSettings):
    enable_cuda: bool = True
    max_vram_usage: float = Field(default=0.85, description="最大 VRAM 使用比例")
    fallback_to_cpu: bool = True


class AIConfig(BaseSettings):
    model_config = {"env_prefix": "MOLDGEN_AI_"}

    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com/v1"
    deepseek_model: str = "deepseek-chat"

    qwen_api_key: str = ""
    qwen_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    qwen_chat_model: str = "qwen-plus"
    qwen_vl_model: str = "qwen-vl-max"

    kimi_api_key: str = ""
    kimi_base_url: str = "https://api.moonshot.cn/v1"
    kimi_model: str = "moonshot-v1-8k"

    wanxiang_api_key: str = ""

    tripo_api_key: str = ""


class ServerConfig(BaseSettings):
    model_config = {"env_prefix": "MOLDGEN_"}

    host: str = "127.0.0.1"
    port: int = 8000
    debug: bool = False
    cors_origins: list[str] = ["http://localhost:1420", "http://localhost:5173"]

    data_dir: Path = Field(default=Path("data"))
    upload_dir: Path = Field(default=Path("data/uploads"))
    project_dir: Path = Field(default=Path("data/projects"))
    cache_dir: Path = Field(default=Path("data/cache"))

    max_upload_size_mb: int = 500

    gpu: GPUConfig = GPUConfig()
    ai: AIConfig = AIConfig()

    def ensure_dirs(self) -> None:
        for d in [self.data_dir, self.upload_dir, self.project_dir, self.cache_dir]:
            d.mkdir(parents=True, exist_ok=True)


def get_config() -> ServerConfig:
    return ServerConfig()
