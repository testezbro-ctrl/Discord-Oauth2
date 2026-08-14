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


@app.get("/")
async def root():
    return {"status": "ok", "service": "dccon-arca-discord-bot-server"}
