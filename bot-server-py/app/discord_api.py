# app/discord_api.py
# 디스코드 REST API 호출 헬퍼. httpx.AsyncClient 사용.

import asyncio
import base64
import json
import os
import re
import unicodedata
from urllib.parse import parse_qsl, urlparse

import httpx

API_BASE = "https://discord.com/api/v10"


def fetch_headers(url: str) -> dict:
    # dcinside(dccon) 등 일부 CDN은 서버(데이터센터 IP)에서 오는 요청을
    # 봇으로 의심해 403으로 막는 경우가 있습니다. 실제 브라우저 요청과
    # 최대한 비슷하게 헤더를 채워 통과율을 높입니다. (100% 보장은 아니라,
    # 아래 재시도 로직과 함께 씁니다)
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
        "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
        "Referer": referer,
        "Sec-Fetch-Dest": "image",
        "Sec-Fetch-Mode": "no-cors",
        "Sec-Fetch-Site": "same-site",
    }


async def fetch_bytes_with_retry(url: str, timeout: float = 30, attempts: int = 3) -> httpx.Response:
    # 일부 CDN은 서버발 요청을 간헐적으로만 차단합니다(요청마다 결과가 다를
    # 수 있음). 바로 포기하지 않고 짧게 기다렸다가 몇 번 더 시도합니다.
    last_res = None
    for i in range(attempts):
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            res = await client.get(url, headers=fetch_headers(url))
        if res.status_code < 400:
            return res
        last_res = res
        if res.status_code in (403, 429) and i < attempts - 1:
            await asyncio.sleep(0.8 * (i + 1))
            continue
        break
    return last_res


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


def sniff_image_format(data: bytes) -> str | None:
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:3] == b"\xff\xd8\xff":
        return "jpg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return None


def ensure_discord_safe_image(data: bytes) -> tuple[bytes, str, str]:
    # 디스코드 커스텀 이모지 API는 PNG/JPEG/GIF만 받습니다 (webp 등은
    # "Invalid Asset" 에러가 남). dccon은 webp로 서빙되는 경우가 있어서,
    # 그런 경우 Pillow로 PNG(정지) 또는 GIF(애니메이션)로 변환합니다.
    fmt = sniff_image_format(data)
    if fmt in ("gif", "png", "jpg"):
        mime_map = {"gif": "image/gif", "png": "image/png", "jpg": "image/jpeg"}
    else:
        from io import BytesIO

        from PIL import Image

        try:
            img = Image.open(BytesIO(data))
            buf = BytesIO()
            if getattr(img, "is_animated", False):
                img.save(buf, format="GIF", save_all=True)
                data, fmt = buf.getvalue(), "gif"
            else:
                img.convert("RGBA").save(buf, format="PNG")
                data, fmt = buf.getvalue(), "png"
        except Exception as err:  # noqa: BLE001
            raise RuntimeError(f"디스코드가 지원하지 않는 이미지 형식이고, 변환도 실패했습니다: {err}") from err
        mime_map = {"gif": "image/gif", "png": "image/png"}

    # 256KB를 넘으면(용량이 큰 GIF 등) 단계적으로 압축해서 맞춥니다.
    if len(data) > 256 * 1024:
        from .image_shrink import shrink_image_to_fit

        data, fmt = shrink_image_to_fit(data, fmt)
        mime_map = {"gif": "image/gif", "png": "image/png", "jpg": "image/jpeg"}

    return data, fmt, mime_map[fmt]


async def url_to_data_uri(url: str) -> str:
    res = await fetch_bytes_with_retry(url, timeout=30)
    if res.status_code >= 400:
        raise RuntimeError(f"이미지를 가져오지 못했습니다 (HTTP {res.status_code})")
    data, _ext, mime = ensure_discord_safe_image(res.content)
    b64 = base64.b64encode(data).decode("ascii")
    return f"data:{mime};base64,{b64}"


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
