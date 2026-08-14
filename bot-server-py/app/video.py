# app/video.py
# 디스코드 이모지 등록 API는 mp4(영상)를 직접 받지 않습니다 (PNG/JPEG/GIF만
# 허용 — 안 지키면 "Invalid Asset"(코드 50046) 에러가 납니다). 그래서
# 아카라이브 등에서 온 mp4 URL은 여기서 먼저 GIF로 변환한 뒃 업로드합니다.
#
# ffmpeg 시스템 설치 없이도 동작하도록, pip로만 설치되는
# imageio-ffmpeg(내장 정적 바이너리)를 사용합니다.

import asyncio
import base64
import os
import subprocess
import tempfile

import httpx
import imageio_ffmpeg

FFMPEG_BIN = imageio_ffmpeg.get_ffmpeg_exe()

MAX_EMOJI_BYTES = 256 * 1024  # 디스코드 이모지 용량 제한

# 용량 제한(256KB) 안에 들어오도록, 해상도/프레임레이트를 점점 낮춰가며
# 재시도하는 단계들입니다. 앞 단계에서 실패하면 다음 단계로 더 압축합니다.
QUALITY_STEPS = [
    {"max_width": 128, "fps": 12},
    {"max_width": 96, "fps": 10},
    {"max_width": 64, "fps": 8},
    {"max_width": 48, "fps": 6},
]

MAX_DURATION_SECONDS = 4  # 너무 긴 영상은 앞부분만 잘라서 변환 (용량 절약)


async def _download(url: str) -> bytes:
    async with httpx.AsyncClient(timeout=60) as client:
        res = await client.get(url)
    if res.status_code >= 400:
        raise RuntimeError(f"영상을 가져오지 못했습니다 (HTTP {res.status_code})")
    return res.content


def _run_ffmpeg(mp4_path: str, gif_path: str, max_width: int, fps: int) -> None:
    cmd = [
        FFMPEG_BIN,
        "-y",
        "-i",
        mp4_path,
        "-t",
        str(MAX_DURATION_SECONDS),
        "-vf",
        f"fps={fps},scale={max_width}:-1:flags=lanczos",
        "-loop",
        "0",
        gif_path,
    ]
    proc = subprocess.run(cmd, capture_output=True)
    if proc.returncode != 0:
        stderr = proc.stderr.decode(errors="ignore")[-500:]
        raise RuntimeError(f"GIF 변환 실패: {stderr}")


async def convert_mp4_url_to_gif_data_uri(url: str) -> str:
    mp4_bytes = await _download(url)

    with tempfile.TemporaryDirectory() as tmp:
        mp4_path = os.path.join(tmp, "in.mp4")
        gif_path = os.path.join(tmp, "out.gif")
        with open(mp4_path, "wb") as f:
            f.write(mp4_bytes)

        last_error: Exception | None = None
        for step in QUALITY_STEPS:
            try:
                # ffmpeg 자체가 무거운 동기 작업이라, 이벤트 루프를 막지
                # 않도록 별도 스레드에서 실행합니다.
                await asyncio.to_thread(_run_ffmpeg, mp4_path, gif_path, step["max_width"], step["fps"])
                gif_bytes = open(gif_path, "rb").read()
                if len(gif_bytes) <= MAX_EMOJI_BYTES:
                    b64 = base64.b64encode(gif_bytes).decode("ascii")
                    return f"data:image/gif;base64,{b64}"
                last_error = RuntimeError(
                    f"{step['max_width']}px/{step['fps']}fps로도 {len(gif_bytes)}바이트라 256KB를 초과합니다."
                )
            except Exception as err:  # noqa: BLE001
                last_error = err

        raise RuntimeError(f"GIF 변환/용량 축소에 실패했습니다: {last_error}")
