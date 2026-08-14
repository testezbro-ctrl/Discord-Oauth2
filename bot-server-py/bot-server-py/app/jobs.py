# app/jobs.py
# "적용/거부" 버튼이 달린 메시지 하나 = job 하나. 메시지 ID를 키로 저장해두면
# 버튼 클릭(interaction) 페이로드에 담겨오는 message.id로 바로 찾아쓸 수
# 있습니다.

_jobs: dict[str, dict] = {}  # messageId -> { guildId, channelId, items, requesterId, status }


def create_job(message_id: str, data: dict) -> None:
    _jobs[message_id] = {"status": "pending", **data}


def get_job(message_id: str) -> dict | None:
    return _jobs.get(message_id)


def update_job(message_id: str, patch: dict) -> dict | None:
    job = _jobs.get(message_id)
    if job is None:
        return None
    job.update(patch)
    return job


def delete_job(message_id: str) -> None:
    _jobs.pop(message_id, None)
