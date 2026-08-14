# app/routers/api.py

from typing import Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from ..discord_api import (
    derive_name_from_url,
    fetch_eligible_guilds,
    send_channel_message,
    send_channel_message_with_file,
)
from ..guild_channels import resolve_channel_for_guild
from ..jobs import create_job
from ..sessions import get_session
from ..video import convert_mp4_url_to_gif_bytes

router = APIRouter(prefix="/api")


def require_session(authorization: Optional[str]) -> dict:
    session_id = authorization[7:] if authorization and authorization.startswith("Bearer ") else None
    session = get_session(session_id) if session_id else None
    if not session:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")
    return session


@router.get("/me")
async def me(authorization: Optional[str] = Header(None)):
    session = require_session(authorization)
    return {"user": session["user"]}


@router.get("/guilds")
async def guilds(authorization: Optional[str] = Header(None)):
    session = require_session(authorization)
    try:
        eligible = await fetch_eligible_guilds(session["accessToken"])
        return {"guilds": eligible}
    except Exception as err:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(err)) from err


class CartItem(BaseModel):
    url: str
    kind: str = "image"
    name: Optional[str] = None


class SendRequest(BaseModel):
    guildId: str
    items: list[CartItem]


@router.post("/send")
async def send(body: SendRequest, authorization: Optional[str] = Header(None)):
    session = require_session(authorization)
    if not body.items:
        raise HTTPException(status_code=400, detail="items가 비어있습니다.")

    channel_id = await resolve_channel_for_guild(body.guildId)
    if not channel_id:
        raise HTTPException(
            status_code=400,
            detail="이 서버에는 전송할 채널이 지정돼 있지 않습니다. config/guildChannels.json에 등록해주세요.",
        )

    first = body.items[0]
    first_name = first.name or derive_name_from_url(first.url)
    extra_count = len(body.items) - 1

    embed = {
        "title": "이모티콘 데이터가 도착했습니다! ⠀⠀",
        "color": 0x00FFF2,
        "description": f"{first_name} 외 {extra_count}개\n이모지에 추가 하시겠습니까?",
    }

    components = [
        {
            "type": 1,
            "components": [
                {"type": 2, "style": 3, "label": "적용", "custom_id": "g", "emoji": {"name": "🔻"}},
                {"type": 2, "style": 4, "label": "거부", "custom_id": "G1", "emoji": {"name": "❌"}},
            ],
        }
    ]

    try:
        if first.kind == "video":
            # 디스코드 임베드 썸네일은 mp4를 직접 못 띄웁니다. 미리 GIF로
            # 변환해서 메시지에 파일로 첨부하고, 그 첨부파일을 썸네일로
            # 가리키도록(attachment://) 합니다.
            gif_bytes = await convert_mp4_url_to_gif_bytes(first.url)
            embed["thumbnail"] = {"url": "attachment://thumb.gif"}
            payload = {"embeds": [embed], "components": components}
            message = await send_channel_message_with_file(channel_id, payload, "thumb.gif", gif_bytes)
        else:
            embed["thumbnail"] = {"url": first.url}
            payload = {"embeds": [embed], "components": components}
            message = await send_channel_message(channel_id, payload)
    except Exception as err:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(err)) from err

    create_job(
        message["id"],
        {
            "guildId": body.guildId,
            "channelId": channel_id,
            "items": [item.model_dump() for item in body.items],
            "requesterId": session["user"]["id"],
        },
    )

    return {"ok": True, "messageId": message["id"]}
