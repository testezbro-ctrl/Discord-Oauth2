# run.py
import os

import uvicorn
from dotenv import load_dotenv

load_dotenv()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 3787))
    print(f"서버 실행 중: http://localhost:{port}")
    print(f"- 로그인 시작: http://localhost:{port}/auth/discord/login")
    print(f"- interactions endpoint(터널 필요): http://localhost:{port}/interactions")
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, reload=True)
