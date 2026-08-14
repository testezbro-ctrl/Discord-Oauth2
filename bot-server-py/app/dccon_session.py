# app/dccon_session.py
# dccon.dcinside.com의 이미지 서버는 Referer 헤더만으로는 부족하고,
# 먼저 세션 쿠키(ci_c)를 받아온 뒤 그 값을 package_detail API에 인증
# 토큰(ci_t)으로 제출해야 실제 이미지에 접근할 수 있습니다.
# (공개된 dccon 다운로더 스크립트의 흐름을 그대로 따랐습니다)
#
#   1) GET  https://dccon.dcinside.com/  → 응답 쿠키에서 ci_c 획득
#   2) POST https://dccon.dcinside.com/index/package_detail
#      (X-Requested-With: XMLHttpRequest)
#      data={ci_t: ci_c값, package_idx: 팩 번호} → 이 시점부터 세션이
#      그 팩의 이미지에 접근 가능한 상태가 됨
#   3) 그 세션(쿠키 유지)으로 실제 이미지 URL을 GET

import httpx

from .discord_api import ensure_discord_safe_image

ROOT_URL = "https://dccon.dcinside.com/"
PACKAGE_DETAIL_URL = "https://dccon.dcinside.com/index/package_detail"

_XHR_HEADERS = {"X-Requested-With": "XMLHttpRequest"}

# package_id -> httpx.AsyncClient (쿠키 유지). 같은 팩의 여러 이미지를
# 받을 때 매번 핸드셰이크를 반복하지 않도록 잡(job) 실행 동안 캐싱합니다.
_session_cache: dict[str, httpx.AsyncClient] = {}


async def get_dccon_session(package_id: str) -> httpx.AsyncClient:
    cached = _session_cache.get(package_id)
    if cached is not None:
        return cached

    client = httpx.AsyncClient(timeout=30, follow_redirects=True)
    r = await client.get(ROOT_URL)
    ci_c = r.cookies.get("ci_c")
    if not ci_c:
        await client.aclose()
        raise RuntimeError("dccon 세션 쿠키(ci_c)를 받지 못했습니다.")

    await client.post(
        PACKAGE_DETAIL_URL,
        headers=_XHR_HEADERS,
        data={"ci_t": ci_c, "package_idx": package_id},
    )

    _session_cache[package_id] = client
    return client


async def fetch_dccon_image_bytes(url: str, package_id: str) -> tuple[bytes, str]:
    client = await get_dccon_session(package_id)
    res = await client.get(url, headers={"Referer": "https://dccon.dcinside.com/hot/1"})
    if res.status_code >= 400:
        raise RuntimeError(f"이미지를 가져오지 못했습니다 (HTTP {res.status_code})")
    data, _ext, mime = ensure_discord_safe_image(res.content)
    if len(data) > 256 * 1024:
        raise RuntimeError("이미지 용량이 256KB를 넘어 디스코드 이모지로 등록할 수 없습니다.")
    return data, mime


async def close_all_sessions() -> None:
    for client in _session_cache.values():
        await client.aclose()
    _session_cache.clear()
