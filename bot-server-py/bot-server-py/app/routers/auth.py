# app/routers/auth.py
# 브라우저가 직접 디스코드로 리다이렉트되는 표준 OAuth2 authorization code
# flow라, 이 부분은 로컬(http://localhost)만으로도 문제없이 동작합니다.
# (Discord 서버가 우리 서버에 직접 요청을 보내는 게 아니라, 사용자의
#  브라우저가 왔다갔다 하는 것이기 때문입니다)

import os
from urllib.parse import urlencode

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from ..discord_api import exchange_code_for_token, fetch_discord_user
from ..sessions import create_session

router = APIRouter(prefix="/auth")


@router.get("/discord/login")
async def discord_login():
    params = {
        "client_id": os.environ["DISCORD_CLIENT_ID"],
        "redirect_uri": os.environ["OAUTH_REDIRECT_URI"],
        "response_type": "code",
        "scope": "identify guilds",
        "prompt": "consent",
    }
    return RedirectResponse(f"https://discord.com/oauth2/authorize?{urlencode(params)}")


@router.get("/discord/callback")
async def discord_callback(request: Request):
    code = request.query_params.get("code")
    error = request.query_params.get("error")

    if error:
        return HTMLResponse(
            _render_result_page(False, f"디스코드에서 로그인을 거부했습니다: {error}"), status_code=400
        )
    if not code:
        return HTMLResponse(_render_result_page(False, "인증 코드가 없습니다."), status_code=400)

    try:
        token = await exchange_code_for_token(code)
        user = await fetch_discord_user(token["access_token"])
        session_id = create_session(token["access_token"], user)
        query = urlencode({"sessionId": session_id, "username": user["username"]})
        return RedirectResponse(f"/auth/success?{query}")
    except Exception as err:  # noqa: BLE001
        return HTMLResponse(_render_result_page(False, f"로그인 처리 중 오류: {err}"), status_code=500)


@router.get("/success")
async def success(request: Request):
    username = request.query_params.get("username", "")
    return HTMLResponse(_render_result_page(True, f"{username}님, 로그인 완료! 이 창은 자동으로 닫힙니다."))


def _render_result_page(ok: bool, message: str) -> str:
    icon = "✅" if ok else "⚠️"
    return f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8" />
<style>
  body {{ font-family: -apple-system, sans-serif; display:flex; align-items:center; justify-content:center;
         height:100vh; margin:0; background:#111827; color:#fff; }}
  .box {{ text-align:center; padding:24px; }}
  .icon {{ font-size:40px; margin-bottom:12px; }}
</style>
</head>
<body>
  <div class="box">
    <div class="icon">{icon}</div>
    <p>{message}</p>
  </div>
  <script>setTimeout(() => window.close(), 1500);</script>
</body></html>"""
