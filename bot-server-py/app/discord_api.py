# app/discord_api.py
# 디스코드 REST API 호출 헬퍼. httpx.AsyncClient 사용.

import base64
import os
import re
import unicodedata

import httpx

API_BASE = "https://discord.com/api/v10"


def _bot_headers() -> dict:
    return {
        "Authorization": f"Bot {os.environ['DISCORD_BOT_TOKEN']}",
        "Content-Type": "application/json",
    }


async def _discord_request(method: str, path: str, **kwargs) -> httpx.Response:
    async with httpx.AsyncClient(timeout=30) as client:
        res = await client.request(method, f"{API_BASE}{path}", **kwargs)
        if res.status_code == 429:
            body = res.json() if res.content else {}
            retry_after = float(body.get("retry_after", 1))
            import asyncio

            await asyncio.sleep(retry_after)
            return await _discord_request(method, path, **kwargs)
        return res


# ---------- OAuth2 ----------
async def exchange_code_for_token(code: str) -> dict:
    data = {
        "client_id": os.environ["DISCORD_CLIENT_ID"],
        "client_secret": os.environ["DISCORD_CLIENT_SECRET"],
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": os.environ["OAUTH_REDIRECT_URI"],
    }
    async with httpx.AsyncClient(timeout=30) as client:
        res = await client.post(
            f"{API_BASE}/oauth2/token",
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
    if res.status_code >= 400:
        raise RuntimeError(f"토큰 교환 실패 (HTTP {res.status_code}): {res.text}")
    return res.json()


async def fetch_discord_user(access_token: str) -> dict:
    async with httpx.AsyncClient(timeout=30) as client:
        res = await client.get(
            f"{API_BASE}/users/@me",
            headers={"Authorization": f"Bearer {access_token}"},
        )
    if res.status_code >= 400:
        raise RuntimeError(f"사용자 정보 조회 실패 (HTTP {res.status_code})")
    return res.json()


async def fetch_user_guilds(access_token: str) -> list:
    async with httpx.AsyncClient(timeout=30) as client:
        res = await client.get(
            f"{API_BASE}/users/@me/guilds",
            headers={"Authorization": f"Bearer {access_token}"},
        )
    if res.status_code >= 400:
        raise RuntimeError(f"사용자 서버 목록 조회 실패 (HTTP {res.status_code})")
    return res.json()


async def fetch_bot_guilds() -> list:
    res = await _discord_request("GET", "/users/@me/guilds", headers=_bot_headers())
    if res.status_code >= 400:
        raise RuntimeError(f"봇 서버 목록 조회 실패 (HTTP {res.status_code})")
    return res.json()


ADMINISTRATOR = 0x8
MANAGE_GUILD_EXPRESSIONS = 0x40000000  # 신규 권한 비트
LEGACY_MANAGE_EMOJIS = 0x40


def can_manage_emojis(permissions_str: str) -> bool:
    try:
        perms = int(permissions_str)
    except (TypeError, ValueError):
        return False
    return bool(
        perms & ADMINISTRATOR or perms & MANAGE_GUILD_EXPRESSIONS or perms & LEGACY_MANAGE_EMOJIS
    )


async def fetch_eligible_guilds(access_token: str) -> list:
    user_guilds, bot_guilds = await fetch_user_guilds(access_token), await fetch_bot_guilds()
    bot_guild_ids = {g["id"] for g in bot_guilds}
    result = []
    for g in user_guilds:
        if g["id"] in bot_guild_ids and can_manage_emojis(g.get("permissions", "0")):
            icon = (
                f"https://cdn.discordapp.com/icons/{g['id']}/{g['icon']}.png" if g.get("icon") else None
            )
            result.append({"id": g["id"], "name": g["name"], "icon": icon})
    return result


# ---------- 메시지 ----------
async def send_channel_message(channel_id: str, payload: dict) -> dict:
    res = await _discord_request(
        "POST", f"/channels/{channel_id}/messages", headers=_bot_headers(), json=payload
    )
    if res.status_code >= 400:
        raise RuntimeError(f"메시지 전송 실패 (HTTP {res.status_code}): {res.text}")
    return res.json()


async def edit_channel_message(channel_id: str, message_id: str, payload: dict) -> dict:
    res = await _discord_request(
        "PATCH",
        f"/channels/{channel_id}/messages/{message_id}",
        headers=_bot_headers(),
        json=payload,
    )
    if res.status_code >= 400:
        raise RuntimeError(f"메시지 수정 실패 (HTTP {res.status_code}): {res.text}")
    return res.json()


# ---------- 이모지 ----------
async def create_guild_emoji(guild_id: str, name: str, image_data_uri: str) -> dict:
    res = await _discord_request(
        "POST",
        f"/guilds/{guild_id}/emojis",
        headers=_bot_headers(),
        json={"name": name, "image": image_data_uri},
    )
    if res.status_code >= 400:
        raise RuntimeError(f"이모지 등록 실패 (HTTP {res.status_code}): {res.text}")
    return res.json()


async def url_to_data_uri(url: str) -> str:
    async with httpx.AsyncClient(timeout=30) as client:
        res = await client.get(url)
    if res.status_code >= 400:
        raise RuntimeError(f"이미지를 가져오지 못했습니다 (HTTP {res.status_code})")
    content_type = res.headers.get("content-type", "image/gif")
    data = res.content
    if len(data) > 256 * 1024:
        raise RuntimeError("이미지 용량이 256KB를 넘어 디스코드 이모지로 등록할 수 없습니다.")
    b64 = base64.b64encode(data).decode("ascii")
    return f"data:{content_type};base64,{b64}"


def sanitize_emoji_name(raw_name: str | None, fallback_index: int) -> str:
    name = unicodedata.normalize("NFKD", raw_name or "")
    name = re.sub(r"[^a-zA-Z0-9_]", "_", name)
    name = re.sub(r"_+", "_", name).strip("_")
    if not name:
        name = f"emoji_{fallback_index}"
    if len(name) < 2:
        name = name.ljust(2, "_")
    return name[:32]
