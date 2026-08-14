# app/routers/interactions.py
# 디스코드가 우리 서버로 직접 POST 하는 HTTP Interactions Endpoint 입니다.
# 로컬에서 테스트한다면 ngrok 등으로 공인 HTTPS 주소를 만들어, 디스코드
# 개발자 포털 → General Information → Interactions Endpoint URL에
# "https://그주소/interactions" 를 등록해야 디스코드가 여기로 요청을 보낼
# 수 있습니다. (공인 도메인으로 직접 호스팅한다면 그 주소를 바로 쓰면 됩니다)

import os

from fastapi import APIRouter, HTTPException, Request
from nacl.exceptions import BadSignatureError
from nacl.signing import VerifyKey

from ..discord_api import create_guild_emoji, edit_channel_message, sanitize_emoji_name, url_to_data_uri
from ..guild_channels import set_channel_for_guild
from ..jobs import delete_job, get_job, update_job

router = APIRouter()

TOTAL_BLOCKS = 7  # "■■■□□□□" 진행바 칸 수

PING = 1
APPLICATION_COMMAND = 2
MESSAGE_COMPONENT = 3

PONG = 1
CHANNEL_MESSAGE_WITH_SOURCE = 4
DEFERRED_UPDATE_MESSAGE = 6
UPDATE_MESSAGE = 7

EPHEMERAL = 64  # 명령어를 실행한 사람에게만 보이는 응답 플래그


async def verify_discord_signature(request: Request) -> bytes:
    signature = request.headers.get("X-Signature-Ed25519")
    timestamp = request.headers.get("X-Signature-Timestamp")
    body = await request.body()

    if not signature or not timestamp:
        raise HTTPException(status_code=401, detail="서명 헤더가 없습니다.")

    try:
        verify_key = VerifyKey(bytes.fromhex(os.environ["DISCORD_PUBLIC_KEY"]))
        verify_key.verify(f"{timestamp}".encode() + body, bytes.fromhex(signature))
    except (BadSignatureError, ValueError) as err:
        raise HTTPException(status_code=401, detail="서명이 유효하지 않습니다.") from err

    return body


@router.post("/interactions")
async def interactions(request: Request):
    import json

    body = await verify_discord_signature(request)
    interaction = json.loads(body)

    if interaction["type"] == PING:
        return {"type": PONG}

    if interaction["type"] == APPLICATION_COMMAND:
        return handle_slash_command(interaction)

    if interaction["type"] == MESSAGE_COMPONENT:
        message_id = interaction.get("message", {}).get("id")
        job = get_job(message_id) if message_id else None

        if not job:
            return {
                "type": UPDATE_MESSAGE,
                "data": {
                    "embeds": [{"title": "이미 처리되었거나 만료된 요청이에요.", "color": 0x808080}],
                    "components": [],
                },
            }

        custom_id = interaction["data"]["custom_id"]

        if custom_id == "G1":
            delete_job(message_id)
            return {
                "type": UPDATE_MESSAGE,
                "data": {
                    "embeds": [{"title": "요청을 취소했습니다.", "color": 0x808080}],
                    "components": [],
                },
            }

        if custom_id == "g":
            # 3초 안에 응답해야 하므로, 일단 지연 응답하고 실제 이모지 업로드는
            # 백그라운드 태스크로 이어서 진행합니다.
            import asyncio

            asyncio.create_task(process_job(message_id, job))
            return {"type": DEFERRED_UPDATE_MESSAGE}

    raise HTTPException(status_code=400, detail="지원하지 않는 interaction입니다.")


def handle_slash_command(interaction: dict) -> dict:
    data = interaction.get("data", {})
    name = data.get("name")

    if name == "채널설정":
        guild_id = interaction.get("guild_id")
        options = data.get("options", [])
        channel_option = next((opt for opt in options if opt.get("name") == "채널"), None)
        channel_id = channel_option.get("value") if channel_option else None

        if not guild_id or not channel_id:
            return {
                "type": CHANNEL_MESSAGE_WITH_SOURCE,
                "data": {"content": "⚠️ 채널을 지정해주세요.", "flags": EPHEMERAL},
            }

        set_channel_for_guild(guild_id, channel_id)
        return {
            "type": CHANNEL_MESSAGE_WITH_SOURCE,
            "data": {
                "content": f"✅ 이 서버의 이모지 요청 채널을 <#{channel_id}> (으)로 설정했습니다.",
                "flags": EPHEMERAL,
            },
        }

    return {
        "type": CHANNEL_MESSAGE_WITH_SOURCE,
        "data": {"content": "알 수 없는 명령어예요.", "flags": EPHEMERAL},
    }


def progress_bar(percent: int) -> str:
    filled = min(TOTAL_BLOCKS, round((percent / 100) * TOTAL_BLOCKS))
    return "■" * filled + "□" * (TOTAL_BLOCKS - filled)


async def process_job(message_id: str, job: dict) -> None:
    update_job(message_id, {"status": "processing"})
    channel_id = job["channelId"]
    guild_id = job["guildId"]
    items = job["items"]

    success_count = 0
    failed_names: list[str] = []

    for i, item in enumerate(items):
        name = sanitize_emoji_name(item.get("name"), i + 1)
        try:
            data_uri = await url_to_data_uri(item["url"])
            await create_guild_emoji(guild_id, name, data_uri)
            success_count += 1
        except Exception as err:  # noqa: BLE001
            print(f"[이모지 등록 실패] {item['url']}: {err}")
            failed_names.append(name)

        percent = round(((i + 1) / len(items)) * 100)
        try:
            await edit_channel_message(
                channel_id,
                message_id,
                {
                    "embeds": [
                        {
                            "color": 0x00FFFF,
                            "title": "불러온 이미지를 디스코드 이모지에 적용중...",
                            "description": f"{progress_bar(percent)}\n  ({percent}% / 100%)",
                        }
                    ],
                    "components": [],
                },
            )
        except Exception as err:  # noqa: BLE001
            # 편집 요청이 실패해도 업로드 자체는 계속 진행합니다.
            print(f"[진행률 메시지 갱신 실패] {err}")

    summary_lines = [f"✅ 완료: {success_count}개"]
    if failed_names:
        summary_lines.append(f"⚠️ 실패: {len(failed_names)}개 ({', '.join(failed_names)})")

    await edit_channel_message(
        channel_id,
        message_id,
        {
            "embeds": [
                {
                    "color": 0xFFAA00 if failed_names else 0x22C55E,
                    "title": "이모지 적용이 완료됐어요 (일부 실패)"
                    if failed_names
                    else "이모지 적용이 완료됐습니다! 🎉",
                    "description": "\n".join(summary_lines),
                }
            ],
            "components": [],
        },
    )

    delete_job(message_id)
