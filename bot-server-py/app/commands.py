# app/commands.py
# 앱 시작 시 자동으로 등록/갱신되는 글로벌 슬래시 명령어 목록입니다.
# (같은 이름으로 PUT하면 기존 정의를 덮어쓰므로 재배포 때마다 불러도 안전합니다)

MANAGE_GUILD_PERMISSION = "32"  # 0x20, "서버 관리" 권한 비트 — 이 권한 있는 사람만 명령어가 보이고 실행됩니다.

COMMANDS = [
    {
        "name": "채널설정",
        "description": "이 서버에서 이모지 요청 메시지를 받을 채널을 설정합니다.",
        "type": 1,  # CHAT_INPUT (슬래시 명령어)
        "default_member_permissions": MANAGE_GUILD_PERMISSION,
        "dm_permission": False,
        "options": [
            {
                "type": 7,  # CHANNEL
                "name": "채널",
                "description": "이모지 요청을 받을 텍스트 채널",
                "required": True,
                "channel_types": [0],  # GUILD_TEXT
            }
        ],
    }
]
