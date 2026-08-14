# app/discord_api.py
# 디스코드 REST API 호출 헬퍼. httpx.AsyncClient 사용.

import base64
import json
import os
import re
import unicodedata
from urllib.parse import parse_qsl, urlparse

import httpx

API_BASE = "https://discord.com/api/v10"


def fetch_headers(url: str) -> dict:
    # dcinside(dccon) 등 일부 CDN은 Referer/User-Agent가 없는 서버발 요청을
    # 핫링크 방지로 403 차단합니다. 실제 브라우저에서 보는 것과 비슷한
    # 헤더를 붙여서 우회합니다.
    host = urlparse(url).hostname or ""
    if "dcinside.com" in host:
        referer = "https://dccon.dcinside.com/"
    elif "arca.live" in host:
        referer = "https://arca.live/"
    else:
        referer = f"{urlparse(url).scheme}://{host}/"
    return {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
        ),
        "Referer": referer,
    }


def derive_name_from_url(url: str) -> str:
    # 이름(alt/title 등)을 못 찾았을 때 쓰는 폴백입니다. URL 경로의 마지막
    # 조각(확장자 제외)을 기본으로 쓰고, PHP 엔드포인트처럼 경로가 다 같은
    # 경우를 대비해 쿼리스트링의 식별자 값도 붙입니다.
    try:
        parsed = urlparse(url)
        base = (parsed.path.rsplit("/", 1)[-1] or "이모티콘").rsplit(".", 1)[0]
        if parsed.query:
            params = dict(parse_qsl(parsed.query))
            id_like = next((v for v in reversed(list(params.values())) if v.isalnum()), None)
            if id_like:
                return f"{base}-{id_like}"
        return base
    except Exception:  # noqa: BLE001
        return "이모티콘"


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


async def send_channel_message_with_file(
    channel_id: str, payload: dict, filename: str, file_bytes: bytes, content_type: str = "image/gif"
) -> dict:
    # 임베드의 thumbnail.url을 "attachment://파일명" 으로 지정해두면, 이
    # multipart 요청에 같이 첨부한 파일을 그대로 썸네일로 씁니다.
    # (mp4 URL은 임베드 썸네일로 직접 못 쓰므로, 변환된 GIF를 파일로 첨부)
    headers = {"Authorization": f"Bot {os.environ['DISCORD_BOT_TOKEN']}"}
    files = {"files[0]": (filename, file_bytes, content_type)}
    data = {"payload_json": json.dumps(payload, ensure_ascii=False)}

    res = await _discord_request(
        "POST", f"/channels/{channel_id}/messages", headers=headers, files=files, data=data
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
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        res = await client.get(url, headers=fetch_headers(url))
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


# ---------- 슬래시 명령어 등록 ----------
async def register_global_commands(commands: list) -> None:
    app_id = os.environ["DISCORD_CLIENT_ID"]
    async with httpx.AsyncClient(timeout=30) as client:
        res = await client.put(
            f"{API_BASE}/applications/{app_id}/commands",
            headers=_bot_headers(),
            json=commands,
        )
    if res.status_code >= 400:
        raise RuntimeError(f"명령어 등록 실패 (HTTP {res.status_code}): {res.text}")
