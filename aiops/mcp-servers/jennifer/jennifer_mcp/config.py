"""설정 로딩.

- 서버 목록: JENNIFER_SERVERS_FILE (기본 config/servers.json). 토큰은 넣지 않습니다.
- 토큰: 서버마다 token_env 에 적힌 환경 변수에서 읽습니다 (D-10 서버별 토큰 분리).
- 엔드포인트 경로: JENNIFER_ENDPOINTS_FILE (기본 config/endpoints.json).
  Swagger로 확인한 실제 경로로 이 파일만 고치면 됩니다(코드 수정 최소화, 설계 13.4).
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

DEFAULT_PARAMS = {"domain_id": "domain_id", "instance_id": "instance_id", "start_time": "start_time",
                  "end_time": "end_time", "metrics": "metrics", "txid": "txid"}


def _env_bool(name: str, default: bool) -> bool:
    v = os.getenv(name)
    if v is None or v.strip() == "":
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class ServerConf:
    name: str
    label: str
    url: str
    token_env: str
    timeout: float = 10.0
    min_interval: float = 0.2

    @property
    def token(self) -> str:
        return os.getenv(self.token_env, "").strip()


@dataclass
class Settings:
    servers: dict[str, ServerConf]
    endpoints: dict[str, str]
    allowlist: list[str]
    params: dict[str, str] = field(default_factory=dict)
    enabled: bool = False
    log_dir: Path = field(default_factory=lambda: Path("/logs"))
    max_items: int = 200
    max_bytes: int = 2_000_000


def _read_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_settings() -> Settings:
    servers_file = Path(os.getenv("JENNIFER_SERVERS_FILE", BASE_DIR / "config" / "servers.json"))
    if not servers_file.exists():
        servers_file = BASE_DIR / "config" / "servers.example.json"
    endpoints_file = Path(os.getenv("JENNIFER_ENDPOINTS_FILE", BASE_DIR / "config" / "endpoints.json"))

    raw = _read_json(servers_file)
    servers: dict[str, ServerConf] = {}
    for s in raw.get("servers", []):
        conf = ServerConf(
            name=s["name"], label=s.get("label", s["name"]), url=s["url"].rstrip("/"),
            token_env=s["token_env"], timeout=float(s.get("timeout", 10)),
            min_interval=float(s.get("min_interval", 0.2)),
        )
        servers[conf.name] = conf

    ep = _read_json(endpoints_file) if endpoints_file.exists() else {}
    endpoints = {k: v for k, v in ep.get("endpoints", {}).items() if isinstance(v, str)}
    allowlist = list(ep.get("allowlist", [])) or sorted(set(endpoints.values()))

    return Settings(
        servers=servers,
        endpoints=endpoints,
        allowlist=allowlist,
        params={**DEFAULT_PARAMS, **{k: v for k, v in ep.get("params", {}).items()
                                     if isinstance(v, str) and not k.startswith("_")}},
        enabled=_env_bool("JENNIFER_MCP_ENABLED", False),
        log_dir=Path(os.getenv("JENNIFER_CALL_LOG_DIR", "/logs")),
        max_items=int(os.getenv("JENNIFER_MAX_ITEMS", "200")),
        max_bytes=int(os.getenv("JENNIFER_MAX_BYTES", "2000000")),
    )
