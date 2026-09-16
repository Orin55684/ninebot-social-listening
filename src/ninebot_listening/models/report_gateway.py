"""Explicitly authorized official DeepSeek gateway for topic reports only."""
import os
from pathlib import Path
from .deepseek import DeepSeekConfig,DeepSeekGateway
from .base import DataClassification,ModelConfigurationError

class OfficialReportGateway(DeepSeekGateway):
    _ALLOWED_DATA=frozenset({DataClassification.SYNTHETIC,DataClassification.PUBLIC,DataClassification.COMPANY_APPROVED})

def report_gateway():
    path=Path(__file__).resolve().parents[3]/'.env.deepseek.local'
    if path.exists():
        for line in path.read_text().splitlines():
            k,sep,v=line.partition('=')
            if sep and k.strip().startswith('DEEPSEEK_'):os.environ[k.strip()]=v.strip().strip('\"\'')
    if not os.environ.get('DEEPSEEK_API_KEY'):raise ModelConfigurationError('尚未配置 DeepSeek 官方 API Key')
    cfg=DeepSeekConfig.from_env()
    if cfg.base_url.rstrip('/') not in ('https://api.deepseek.com','https://api.deepseek.com/v1'):raise ModelConfigurationError('专项报告仅允许已配置的 DeepSeek 官方地址')
    return OfficialReportGateway(cfg)
