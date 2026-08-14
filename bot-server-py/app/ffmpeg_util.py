# app/ffmpeg_util.py
# ffmpeg 바이너리 경로를 한 곳에서만 구해서 여러 모듈이 공유합니다.
# (video.py와 image_shrink.py가 서로를 import하지 않도록 분리해뒀습니다 —
#  discord_api.py -> image_shrink.py -> (X) video.py 순환 참조 방지)

import imageio_ffmpeg

FFMPEG_BIN = imageio_ffmpeg.get_ffmpeg_exe()
