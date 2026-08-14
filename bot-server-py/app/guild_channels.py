# app/guild_channels.py
# config/guildChannels.json 에서 "이 서버는 이 채널로 보낸다"를 읽어옵니다.
# 파일을 수정할 때마다 서버를 재시작할 필요 없이 매번 새로 읽습니다.

import json
from pathlib import Path

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "guildChannels.json"


def resolve_channel_for_guild(guild_id: str) -> str | None:
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        return data.get(guild_id)
    except Exception as err:  # noqa: BLE001
        print(f"guildChannels.json을 읽지 못했습니다: {err}")
        return None
