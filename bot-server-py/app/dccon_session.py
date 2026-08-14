# app/dccon_session.py
# 처음엔 "쿠키 핸드셰이크가 이미지 요청에도 꼭 필요하다"고 가정하고 만들었는데,
# 실제로 테스트해보니 대부분의 공개 디시콘 이미지는 Referer 헤더만으로도
# 200이 떨어졌습니다 (핸드셰이크 있는 방식과 응답 크기까지 동일).
# 그래서 구조를 이렇게 바꿨습니다:
#   1차: Referer만으로 빠르게 시도 (대부분 이걸로 끝남)
#   2차(폴백): 그래도 막히면(구매/비공개 디시콘 등 인증 필요한 경우 대비)
#             세션 쿠키 핸드셰이크를 거쳐 재시도
#
# 핸드셰이크 흐름(2차 폴백에서만 사용):
#   1) GET  https://dccon.dcinside.com/  → 응답 쿠키에서 ci_c 획득
#   2) POST https://dccon.dcinside.com/index/package_detail
#      (X-Requested-With: XMLHttpRequest)
#      data={ci_t: ci_c값, package_idx: 팩 번호}
#   3) 그 세션(쿠키 유지)으로 실제 이미지 URL을 GET

from typing import Optional

import httpx

from .discord_api import ensure_discord_safe_image, fetch_bytes_with_retry

ROOT_URL = "https://dccon.dcinside.com/"
PACKAGE_DETAIL_URL = "https://dccon.dcinside.com/index/package_detail"
IMAGE_REFERER = "https://dccon.dcinside.com/hot/1"

_XHR_HEADERS = {"X-Requested-With": "XMLHttpRequest"}

# package_id -> httpx.AsyncClient (쿠키 유지). 폴백이 실제로 발생했을 때만
# 만들어지고, 같은 팩의 다음 이미지부터는 재사용됩니다.
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


async def fetch_dccon_image_bytes(url: str, package_id: Optional[str] = None) -> tuple[bytes, str]:
    # 1차: 빠른 경로 (Referer만, 재시도 포함)
    res = await fetch_bytes_with_retry(url, timeout=30, attempts=2)
    if res.status_code >= 400 and package_id:
        # 2차: 세션 핸드셰이크를 거쳐 한 번 더 시도
        client = await get_dccon_session(package_id)
        res = await client.get(url, headers={"Referer": IMAGE_REFERER})

    if res.status_code >= 400:
        raise RuntimeError(f"이미지를 가져오지 못했습니다 (HTTP {res.status_code})")

    data, _ext, mime = ensure_discord_safe_image(res.content)
    return data, mime


async def close_all_sessions() -> None:
    for client in _session_cache.values():
        await client.aclose()
    _session_cache.clear()
