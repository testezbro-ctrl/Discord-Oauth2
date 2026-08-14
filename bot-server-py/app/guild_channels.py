# app/guild_channels.py
# "이 서버는 이모지 요청을 이 채널로 받는다"는 매핑을 저장/조회합니다.
#
# - SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY 환경변수가 있으면 Supabase
#   (PostgREST REST API)에 저장합니다. Railway를 재배포해도 Supabase는
#   완전히 별개의 서비스라 값이 안 날아갑니다.
# - 두 환경변수가 없으면(로컬 개발 등) config/guildChannels.json 파일에
#   저장하는 예전 방식으로 자동 폴백합니다.
#
# Supabase 프로젝트에는 아래 테이블이 미리 있어야 합니다 (SQL Editor에서 실행):
#
#   create table guild_channels (
#     guild_id text primary key,
#     channel_id text not null,
#     updated_at timestamptz default now()
#   );

import json
import os
from pathlib import Path
from typing import Optional

import httpx

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "guildChannels.json"

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
USE_SUPABASE = bool(SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY)

_file_cache: Optional[dict] = None


# ---------- Supabase(REST/PostgREST) 기반 구현 ----------
def _supabase_headers() -> dict:
    return {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": "application/json",
    }


async def _supabase_get(guild_id: str) -> Optional[str]:
    async with httpx.AsyncClient(timeout=15) as client:
        res = await client.get(
            f"{SUPABASE_URL}/rest/v1/guild_channels",
            headers=_supabase_headers(),
            params={"guild_id": f"eq.{guild_id}", "select": "channel_id"},
        )
    if res.status_code >= 400:
        print(f"[guild_channels] Supabase 조회 실패: {res.status_code} {res.text}")
        return None
    rows = res.json()
    return rows[0]["channel_id"] if rows else None


async def _supabase_set(guild_id: str, channel_id: str) -> None:
    async with httpx.AsyncClient(timeout=15) as client:
        res = await client.post(
            f"{SUPABASE_URL}/rest/v1/guild_channels",
            headers={**_supabase_headers(), "Prefer": "resolution=merge-duplicates"},
            json={"guild_id": guild_id, "channel_id": channel_id},
        )
    if res.status_code >= 400:
        raise RuntimeError(f"Supabase 저장 실패: {res.status_code} {res.text}")


# ---------- 파일 기반 폴백 (SUPABASE_URL 미설정 시, 로컬 개발용) ----------
def _load_file() -> dict:
    global _file_cache
    if _file_cache is not None:
        return _file_cache
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception as err:  # noqa: BLE001
        print(f"guildChannels.json을 읽지 못했습니다: {err}")
        data = {}
    data.pop("_comment", None)
    _file_cache = data
    return _file_cache


def _file_get(guild_id: str) -> Optional[str]:
    return _load_file().get(guild_id)


def _file_set(guild_id: str, channel_id: str) -> None:
    data = _load_file()
    data[guild_id] = channel_id
    try:
        CONFIG_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as err:  # noqa: BLE001
        print(f"guildChannels.json 저장 실패(재시작 시 초기화될 수 있음): {err}")


# ---------- 공개 API (다른 모듈은 이 두 함수만 사용하면 됨) ----------
async def resolve_channel_for_guild(guild_id: str) -> Optional[str]:
    if USE_SUPABASE:
        return await _supabase_get(guild_id)
    return _file_get(guild_id)


async def set_channel_for_guild(guild_id: str, channel_id: str) -> None:
    if USE_SUPABASE:
        await _supabase_set(guild_id, channel_id)
    else:
        _file_set(guild_id, channel_id)
