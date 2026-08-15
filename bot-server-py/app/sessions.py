# app/sessions.py
# 로컬/원격 어디든 이 프로세스가 살아있는 동안만 유지되는 인메모리 세션
# 저장소입니다. (운영에선 redis/DB 등으로 교체 권장)

import uuid
from typing import Optional

_sessions: dict[str, dict] = {}  # sessionId -> { accessToken, user }
_pending_logins: dict[str, dict] = {}  # loginId(state) -> { sessionId, username }


def create_session(access_token: str, user: dict) -> str:
    session_id = str(uuid.uuid4())
    _sessions[session_id] = {"accessToken": access_token, "user": user}
    return session_id


def get_session(session_id: str) -> Optional[dict]:
    return _sessions.get(session_id)


def register_pending_login(login_id: str, session_id: str, username: str) -> None:
    _pending_logins[login_id] = {"sessionId": session_id, "username": username}


def get_pending_login(login_id: str) -> Optional[dict]:
    return _pending_logins.get(login_id)
