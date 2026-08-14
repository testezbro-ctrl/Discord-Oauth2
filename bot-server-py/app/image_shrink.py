# app/image_shrink.py
# 디스코드 이모지는 256KB를 넘으면 등록이 안 됩니다. mp4->GIF 변환
# (video.py)은 처음부터 이 제한을 감안해 단계적으로 압축하는데, 이미
# GIF/PNG/webp로 받아온 이미지(dccon 등)는 그런 처리가 없어서 그냥
# 실패했었습니다. 이 모듈은 그 이미지들도 같은 방식으로 압축합니다.

import subprocess
import tempfile
from io import BytesIO
from pathlib import Path

from PIL import Image

from .ffmpeg_util import FFMPEG_BIN

MAX_BYTES = 256 * 1024

# 앞 단계에서 용량 초과면 점점 더 작게/거칠게 재시도합니다.
SHRINK_STEPS = [
    {"max_width": 128, "fps": 12},
    {"max_width": 96, "fps": 10},
    {"max_width": 64, "fps": 8},
    {"max_width": 48, "fps": 6},
    {"max_width": 32, "fps": 5},
]


def _is_animated(data: bytes) -> bool:
    try:
        img = Image.open(BytesIO(data))
        return bool(getattr(img, "is_animated", False))
    except Exception:  # noqa: BLE001
        return False


def shrink_image_to_fit(data: bytes, ext: str) -> tuple[bytes, str]:
    if len(data) <= MAX_BYTES:
        return data, ext

    animated = ext in ("gif", "webp") and _is_animated(data)

    with tempfile.TemporaryDirectory() as tmp:
        in_path = Path(tmp) / f"in.{ext}"
        in_path.write_bytes(data)

        last_error = f"원본이 {len(data)}바이트로 이미 256KB를 초과합니다."
        for step in SHRINK_STEPS:
            out_ext = "gif" if animated else "png"
            out_path = Path(tmp) / f"out_{step['max_width']}.{out_ext}"
            scale = f"scale={step['max_width']}:-1:flags=lanczos"

            cmd = [FFMPEG_BIN, "-y", "-i", str(in_path)]
            if animated:
                cmd += ["-vf", f"fps={step['fps']},{scale}", "-loop", "0"]
            else:
                cmd += ["-vf", scale]
            cmd += [str(out_path)]

            proc = subprocess.run(cmd, capture_output=True)
            if proc.returncode != 0:
                last_error = proc.stderr.decode(errors="ignore")[-300:]
                continue

            result = out_path.read_bytes()
            if len(result) <= MAX_BYTES:
                return result, out_ext
            last_error = f"{step['max_width']}px({step['fps']}fps)로 줄여도 {len(result)}바이트라 여전히 초과합니다."

        raise RuntimeError(f"이미지를 256KB 이하로 줄이지 못했습니다: {last_error}")
