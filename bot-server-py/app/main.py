# app/main.py
import os
import sys

from dotenv import load_dotenv

load_dotenv()

REQUIRED_ENV = [
    "DISCORD_CLIENT_ID",
    "DISCORD_CLIENT_SECRET",
    "DISCORD_BOT_TOKEN",
    "DISCORD_PUBLIC_KEY",
    "OAUTH_REDIRECT_URI",
]
missing = [k for k in REQUIRED_ENV if not os.environ.get(k)]
if missing:
    print(f".env에 다음 값이 비어있습니다: {', '.join(missing)}")
    print(".env.example을 복사해서 .env를 만들고 채워주세요.")
    sys.exit(1)

from fastapi import FastAPI  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402

from .commands import COMMANDS  # noqa: E402
from .discord_api import register_global_commands  # noqa: E402
from .routers import api, auth, interactions  # noqa: E402

app = FastAPI(title="dccon-arca-discord-bot-server")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 로컬 개발 편의를 위해 전체 허용 (운영 시 origin 제한 권장)
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(api.router)
app.include_router(interactions.router)


@app.on_event("startup")
async def _register_commands_on_startup():
    # 같은 이름으로 다시 PUT하면 기존 정의를 덮어쓰는 방식이라, 배포/재시작
    # 때마다 실행해도 안전합니다. (글로벌 명령어는 반영까지 최대 1시간
    # 정도 걸릴 수 있어요)
    try:
        await register_global_commands(COMMANDS)
        print("슬래시 명령어 등록/갱신 완료")
    except Exception as err:  # noqa: BLE001
        print(f"슬래시 명령어 등록 실패: {err}")


@app.get("/")
async def root():
    return {"status": "ok", "service": "dccon-arca-discord-bot-server"}
