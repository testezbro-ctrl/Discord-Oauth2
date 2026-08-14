# app/guild_channels.py
# config/guildChannels.json 에 "이 서버는 이 채널로 보낸다"를 저장합니다.
# /채널설정 슬래시 명령어를 쓰면 여기 값이 실시간으로 갱신됩니다.
#
# 주의(중요): 파일 쓰기는 "지금 떠있는 배포 인스턴스가 살아있는 동안"만
# 유지됩니다. Railway/Render에 새로 배포(재배포)하면 컨테이너가 새로
# 만들어지면서 깃허브 저장소에 커밋된 원본 guildChannels.json으로
# 되돌아갑니다 — 즉 /채널설정으로 등록한 값은 다음 배포 전까지만 유효해요.
# 재배포 없이 오래 유지하고 싶다면 굳이 재배포를 하지 않거나, 나중에
# redis/DB 같은 영구 저장소로 바꾸는 걸 권장합니다.

import json
from pathlib import Path
from typing import Optional

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "guildChannels.json"

_cache: Optional[dict] = None


def _load() -> dict:
    global _cache
    if _cache is not None:
        return _cache
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception as err:  # noqa: BLE001
        print(f"guildChannels.json을 읽지 못했습니다: {err}")
        data = {}
    data.pop("_comment", None)
    _cache = data
    return _cache


def resolve_channel_for_guild(guild_id: str) -> Optional[str]:
    return _load().get(guild_id)


def set_channel_for_guild(guild_id: str, channel_id: str) -> None:
    data = _load()
    data[guild_id] = channel_id
    try:
        CONFIG_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as err:  # noqa: BLE001
        # 파일 쓰기가 실패해도(읽기 전용 파일시스템 등) 인메모리 캐시에는
        # 반영돼 있으므로 현재 실행 중에는 계속 동작합니다.
        print(f"guildChannels.json 저장 실패(재시작 시 초기화될 수 있음): {err}")
