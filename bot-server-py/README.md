# dccon-arca-discord-bot-server (Python / FastAPI)

Node.js 버전과 기능은 동일합니다 (OAuth2 로그인, 서버/채널 조회, 임베드 전송,
적용/거부 버튼 처리, 이모지 업로드 진행률 표시).

## 0. 준비물

- 디스코드 Application/Bot의 **Client ID / Client Secret / Bot Token / Public Key**
  (https://discord.com/developers/applications → 해당 앱 → General Information / OAuth2 / Bot 탭)
- 봇이 이미 초대되어 있는 서버 (Manage Emojis and Stickers 권한 포함해서 초대)
- Python 3.10 이상
- (버튼 클릭 처리를 위해, 공인 도메인이 없다면) [ngrok](https://ngrok.com/) 같은 터널 도구

## 1. 설치

```bash
cd bot-server-py
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

`.env`를 열어 값을 채워주세요.

- `DISCORD_CLIENT_ID`, `DISCORD_CLIENT_SECRET`, `DISCORD_BOT_TOKEN`, `DISCORD_PUBLIC_KEY`
  → 디스코드 개발자 포털에서 복사
- `OAUTH_REDIRECT_URI` → 공인 도메인으로 호스팅한다면 그 주소로,
  로컬 테스트라면 `http://localhost:3787/auth/discord/callback` 그대로 두고
  **디스코드 개발자 포털 → OAuth2 → Redirects에도 정확히 같은 값을 추가**해주세요.

## 2. 서버별 전송 채널 지정

`config/guildChannels.json`을 열어 서버 ID → 채널 ID를 채워주세요.
(디스코드 설정 → 고급 → 개발자 모드 켜기 → 서버/채널 우클릭 → ID 복사)

```json
{
  "123456789012345678": "234567890123456789"
}
```

## 3. 실행 (로컬 개발)

```bash
python run.py
```

`.env`의 `PORT`(기본 3787)로 뜹니다. `http://localhost:3787` 접속해서 확인해보세요.

## 4. Railway / Render로 배포하기 (추천)

로컬 대신 Railway나 Render에 올리면, 별도 터널(ngrok) 없이 배포 즉시 공인 HTTPS
주소가 생겨서 버튼 클릭(Interactions)도 바로 받을 수 있습니다. 이 저장소엔 두
플랫폼 모두를 위한 설정 파일이 이미 들어있어요 (`Procfile`, `railway.json`,
`render.yaml`).

### Railway

1. [railway.app](https://railway.app) 가입 → New Project → **Deploy from GitHub repo**
   (이 `bot-server-py` 폴더를 깃허브 저장소로 올려두고 연결하세요)
2. 프로젝트 → Variables 탭에서 아래 값들을 등록:
   - `DISCORD_CLIENT_ID`, `DISCORD_CLIENT_SECRET`, `DISCORD_BOT_TOKEN`, `DISCORD_PUBLIC_KEY`
   - `OAUTH_REDIRECT_URI` = 나중에 3단계에서 나오는 배포 주소 + `/auth/discord/callback`
     (예: `https://your-app.up.railway.app/auth/discord/callback`)
3. Settings → Networking → **Generate Domain**을 눌러 공인 도메인을 발급받습니다.
4. 발급받은 도메인으로 2번의 `OAUTH_REDIRECT_URI`를 다시 채워 넣고 재배포합니다.
5. `railway.json`이 자동으로 `uvicorn app.main:app --host 0.0.0.0 --port $PORT`로
   실행시켜줍니다. 배포 로그에서 정상 기동을 확인하세요.

### Render

1. [render.com](https://render.com) 가입 → New → **Blueprint** → 이 저장소 연결
   (`render.yaml`을 자동으로 읽어 웹 서비스를 만들어줍니다)
2. 생성 중 `sync: false`로 표시된 환경변수들(`DISCORD_CLIENT_ID` 등)을 입력창에 채워주세요.
3. 배포가 끝나면 `https://dccon-arca-discord-bot-server.onrender.com` 같은 주소가 생깁니다.
4. `OAUTH_REDIRECT_URI` 환경변수를 그 주소 + `/auth/discord/callback`으로 다시
   설정하고 재배포하세요.

> 무료 플랜은 일정 시간 요청이 없으면 슬립 상태로 들어갈 수 있어요(첫 요청이 느릴 수
> 있음). 상시 빠른 응답이 필요하면 유료 플랜을 고려하세요.

### 배포 후 디스코드 개발자 포털 설정

- **OAuth2 → Redirects**: 위에서 정한 `OAUTH_REDIRECT_URI`와 정확히 같은 값 등록
- **General Information → Interactions Endpoint URL**: `https://그 도메인/interactions`
  (서버가 켜져있는 상태에서 저장해야 디스코드의 검증 PING이 통과됩니다)

### 배포 후 확장 프로그램 쪽 주소도 바꿔주세요

`ext/content.js`의 `DISCORD_BACKEND_URL`과 `ext/background.js`의
`DISCORD_BACKEND_ORIGIN` 값을 `http://localhost:3787`에서 배포된 `https://...`
주소로 바꿔주세요.

## 5. (로컬로 할 경우) 버튼(적용/거부) 클릭을 받으려면 — 공인 HTTPS 주소 필요

4번처럼 Railway/Render에 배포했다면 이 단계는 필요 없습니다. 로컬에서만
테스트한다면:

```bash
ngrok http 3787
```

`https://xxxx.ngrok-free.app` 같은 주소가 나오면, 디스코드 개발자 포털 →
General Information → **Interactions Endpoint URL** 에

```
https://xxxx.ngrok-free.app/interactions
```

를 입력하고 저장하세요. (서버가 켜져있어야 검증 PING에 응답할 수 있습니다)

## 6. 확장 프로그램에서 사용하기

확장 프로그램의 장바구니 바 → "디스코드로 보내기" 버튼을 누르면 로그인 → 서버 선택 →
전송까지 그 패널 안에서 진행됩니다. (백엔드 주소를 바꿨다면 4번 마지막 안내대로
`content.js` / `background.js`도 같이 바꿔주세요)

## 참고 / 제약사항

- 세션은 인메모리라 **프로세스를 재시작하면 로그인이 풀립니다.** (운영 시 redis/DB 권장)
- 디스코드 커스텀 이모지 이름은 영문/숫자/밑줄만 허용돼서, 한글 파일명은 자동으로
  `emoji_1`, `emoji_2` 처럼 대체됩니다.
- 이모지 이미지는 256KB를 넘으면 등록에 실패합니다(디스코드 자체 제한).
- 서버의 이모지 슬롯이 가득 찼거나 이름이 중복되면 해당 항목만 실패 처리되고 나머지는 계속 진행됩니다.
- `run.py`는 개발 편의를 위해 `reload=True`로 띄웁니다. 운영 배포 시엔 꺼주세요.
