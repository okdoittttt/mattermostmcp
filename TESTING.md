# Mattermost MCP 동작 검증 가이드

이 문서는 회사 PC에서 처음으로 Mattermost MCP 서버를 띄우고 Claude Desktop과 연결하여 동작을 확인하기 위한 절차입니다. 구현 자체는 끝났지만 사내 Mattermost 서버, 사설 CA, Claude Desktop과 처음 연결해보는 단계이므로 **읽기 → 본인 대상 쓰기 → 안전장치 → 감사 로그** 순서로 단계적으로 검증합니다.

---

## 사전 준비물 (체크리스트)

테스트를 시작하기 전에 아래 항목을 확보하세요.

- [ ] 사내 Mattermost 도메인 (예: `mattermost.mycompany.com`) — 스킴(`https://`)과 포트는 따로 입력합니다.
- [ ] **Personal Access Token**  
  Mattermost 웹에 로그인 → 우상단 프로필 → **Profile → Security → Personal Access Tokens → Create New Token**. 권한이 비활성화돼 있다면 관리자에게 요청 필요.
- [ ] **Python 3.12** 설치 확인  
  이 프로젝트의 `pyproject.toml`은 `requires-python = ">=3.10,<3.14"`이라 Python 3.14, 3.9에서는 의존성 설치가 거부됩니다. 회사 PC에 3.12가 없다면 `brew install python@3.12`로 먼저 설치합니다.
- [ ] **사내 네트워크 사정 파악** — VPN이 필요한지, 프록시가 끼는지, 사설 CA 인증서를 써야 하는지. CA 인증서가 필요하다면 IT에서 PEM 번들 경로를 받아두세요.
- [ ] **Claude Desktop** 최신 버전 설치.

---

## 1단계 — 환경 셋업

집에서 만든 `.venv/`는 Python 3.14로 만들어졌을 가능성이 높아 회사 PC에서는 **새로 만드는 게 안전**합니다. 3.12 기준 venv를 만들고 개발 의존성까지 포함해 editable 모드로 설치한 뒤, 단위 테스트가 통과하는지 한 번 돌려서 기준선을 잡습니다.

```bash
cd ~/Developer/mattermostmcp     # 경로는 실제 위치에 맞게
rm -rf .venv
python3.12 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -e ".[dev]"
pytest
```

- `pip install -e ".[dev]"`까지 통과하면 `mattermost-mcp` 실행 파일이 `.venv/bin/`에 생깁니다. `which mattermost-mcp`로 경로를 확인해두세요. Claude Desktop 설정에 이 절대경로가 필요합니다.
- `pytest`는 현재 `tests/test_safety.py` 하나만 도는데, 여기서 실패하면 그 다음 단계로 넘어가지 마세요.

---

## 2단계 — `.env` 설정

`.env.example`을 복사해 `.env`를 만들고 회사 값으로 채웁니다. `.env`는 `.gitignore`에 들어 있어 커밋되지 않습니다.

```bash
cp .env.example .env
```

채워야 할 값과 의미

| 변수 | 의미 |
|------|------|
| `MM_URL` | 사내 Mattermost 도메인. **스킴·포트 빼고** 호스트만. |
| `MM_TOKEN` | 위에서 발급받은 Personal Access Token. |
| `MM_SCHEME`, `MM_PORT` | 기본값(https, 443) 그대로면 손댈 필요 없음. |
| `MM_VERIFY_SSL` | TLS 검증. **기본 true 유지를 권장.** |
| `MM_CA_BUNDLE` | 사내 사설 CA를 쓴다면 PEM 번들 경로. SSL 오류가 나면 우선 이 옵션부터 시도. `MM_VERIFY_SSL=false`는 최후의 수단입니다. |
| `MM_BLOCKED_CHANNELS` | 읽기를 절대 허용하지 않을 채널 이름(콤마 구분). 예: `hr-private,exec-only`. 안전장치 검증에서 사용. |
| `MM_AUDIT_LOG_PATH` | 감사 로그 파일 경로. 미지정 시 `~/.mattermost-mcp/audit.log`. |

---

## 3단계 — 1회용 인증 스모크 테스트

Claude Desktop을 연결하기 전에, "내 토큰으로 로그인이 되긴 하는가?"만 빠르게 확인합니다. 한 줄짜리 파이썬 명령으로 클라이언트를 띄워 본인의 username이 출력되는지 봅니다.

```bash
.venv/bin/python -c "from mattermost_mcp.server import get_client; c=get_client(); print('OK', c.my_username, c.my_id)"
```

출력 시나리오별 대응

- ✅ `OK <내유저명> <user_id>` — 인증과 통신 모두 성공. 4단계로 진행.
- ❌ **SSL 관련 에러 (`SSLCertVerificationError`, `CERTIFICATE_VERIFY_FAILED` 등)** — 사내 사설 CA 미적용. `MM_CA_BUNDLE`에 PEM 경로를 지정하거나, IT에서 받은 CA를 시스템 키체인에 등록.
- ❌ **401 Unauthorized** — 토큰이 잘못됐거나 만료. Mattermost 설정에서 토큰을 재발급.
- ❌ **연결 타임아웃·DNS 실패** — VPN 미접속 또는 프록시 문제. 회사 표준 VPN을 켜고 다시 시도.
- ❌ **`MissingTokenError`** — `.env`가 venv 활성화된 셸에서 로드되지 않음. 프로젝트 루트에서 명령을 실행했는지 확인.

이 단계가 통과하지 않으면 Claude Desktop 단계로 넘어가도 의미가 없습니다.

---

## 4단계 — Claude Desktop에 MCP 서버 등록

Claude Desktop 설정 파일을 열어 mattermost MCP 서버를 등록합니다.

설정 파일 경로 (macOS)

```
~/Library/Application Support/Claude/claude_desktop_config.json
```

여기에 아래 블록을 추가합니다. `command` 값은 **3단계에서 `which mattermost-mcp`로 확인한 절대경로**를 그대로 넣으세요.

```json
{
  "mcpServers": {
    "mattermost": {
      "command": "/Users/<나의사용자명>/Developer/mattermostmcp/.venv/bin/mattermost-mcp",
      "env": {
        "MM_LOG_LEVEL": "INFO"
      }
    }
  }
}
```

- `.env` 파일은 프로젝트 루트에 있으면 `python-dotenv`가 자동으로 읽기 때문에, Claude Desktop 설정에는 토큰을 노출하지 않아도 됩니다.
- **함정 주의**: Claude Desktop은 창을 닫는 것만으로는 종료되지 않습니다. 메뉴바의 **Claude → Quit**으로 완전히 종료한 뒤 다시 실행해야 새 MCP 설정이 적용됩니다.
- 재실행 후 채팅창 하단의 도구 아이콘(망치 모양 등)을 눌러 `mattermost` 서버가 잡혔는지, 툴 목록이 노출되는지 확인하세요. 안 보이면 6단계의 로그 확인으로.

---

## 5단계 — 실제 툴 호출 검증 (Claude와 대화)

여기서부터는 Claude Desktop 채팅창에서 자연어로 시킵니다. **읽기 → 본인 대상 쓰기 → 안전장치 → 감사 로그** 순서로 진행해 위험을 단계적으로 늘립니다.

### 5-1. 읽기 기능 (안전, 별도 승인 불필요)

각 항목을 Claude에게 자연어로 요청하고 결과를 확인합니다.

- "내가 속한 채널 목록을 보여줘." → `list_my_channels`. 팀별로 채널 목록이 떨어져야 함.
- "안 읽은 메시지를 멘션 많은 순으로 정리해줘." → `get_unread_summary`.
- "`<채널이름>` 채널의 최근 10개 메시지를 보여줘." → `get_channel_messages` (limit=10). 사용자명·시각·본문이 같이 나옴.
- "이 게시물(post_id=...)의 스레드 전체를 보여줘." → `get_thread`.
- "사용자 `<이름>`을 검색해줘." → `search_users`.
- "키워드 `release`로 게시물을 검색해줘." → `search_posts`.

→ 6개 모두 정상 응답이 나와야 다음 단계로.

### 5-2. 쓰기 기능 (반드시 본인 대상)

**처음 쓰기 동작은 무조건 본인에게 보내는 DM으로** 시작하세요. 채널에 잘못된 메시지가 새어나가는 사고를 막을 수 있습니다.

순서

1. "나(`@<내유저명>`)한테 DM으로 `mcp test`라고 보내줘."  
   → 첫 응답은 반드시 `{"status": "confirmation_required", ...}` 형태로 와야 합니다. WriteGuard가 동작하고 있다는 증거입니다.
2. Claude가 메시지 미리보기를 보여주면 "그래, 보내."라고 승인 → 두 번째 호출에서 `confirm=True`로 실제 발송 → Mattermost 클라이언트에서 본인 DM에 메시지가 도착했는지 확인.
3. "방금 보낸 메시지를 `mcp test edited`로 수정해줘." → `edit_message`. 본인 메시지여야만 통과.
4. "방금 메시지에 `:+1:` 리액션 달아줘." → `add_reaction`. 이어서 "리액션 빼줘." → `remove_reaction`.
5. "방금 보낸 메시지 삭제해줘." → `delete_message`.

각 쓰기 작업마다 같은 confirmation_required → 승인 → 실행 패턴이 반복되어야 합니다.

### 5-3. 안전장치 동작 확인

- `.env`의 `MM_BLOCKED_CHANNELS`에 등록한 채널에 대해 "그 채널 최근 메시지 보여줘."  
  → `{"error": "access_denied", ...}` 응답이 와야 정상. 본문은 절대 노출되어선 안 됨.
- 동료의 메시지 ID를 골라 "이 메시지 수정해줘." 시도  
  → 권한 거부로 `{"error": "forbidden", ...}` 응답이 와야 함 (Mattermost API가 403을 돌려주고 `server.py`의 매핑이 forbidden으로 변환).

### 5-4. 감사 로그 확인

쓰기 작업 직후 감사 로그 파일을 직접 열어 한 줄씩 기록되었는지 확인합니다.

```bash
tail -n 20 ~/.mattermost-mcp/audit.log
```

(또는 `.env`에서 `MM_AUDIT_LOG_PATH`를 지정했다면 그 경로)

`send_dm`, `edit_message`, `delete_message` 같은 액션명과 함께 채널/메시지 ID, 본인 username, 길이 등이 JSON으로 들어가 있어야 합니다.

---

## 6단계 — 문제 생겼을 때

### 로그 레벨 올리기

Claude Desktop 설정에서 `MM_LOG_LEVEL`을 `DEBUG`로 바꾸고 Claude Desktop을 완전 종료 후 재실행.

```json
"env": { "MM_LOG_LEVEL": "DEBUG" }
```

### Claude Desktop 쪽 로그 위치

```
~/Library/Logs/Claude/mcp-server-mattermost.log
```

여기에 MCP 서버의 stderr 출력이 그대로 들어갑니다. 서버 부팅 실패, 인증 실패, 예외 스택은 거의 다 여기서 잡힙니다.

### 서버를 수동으로 띄워 직접 보기

stdio 모드라 단독 실행해도 외부에서 호출할 수는 없지만, 부팅 단계의 에러를 확인하기엔 가장 빠른 방법입니다.

```bash
MM_LOG_LEVEL=DEBUG .venv/bin/mattermost-mcp
```

종료는 Ctrl+C. 정상 부팅된다면 아무 출력 없이 입력을 대기하는 상태가 됩니다.

---

## 검증 완료 기준

아래 4가지가 모두 만족되면 "동작 검증 완료"로 봅니다.

- [ ] 3단계 스모크에서 본인 username이 출력됨
- [ ] 5-1의 읽기 툴 6개가 모두 정상 응답
- [ ] 5-2에서 본인 DM에 대해 발송 → 수정 → 삭제 사이클이 1회 성공하고, 5-4 감사 로그에 최소 3줄이 기록됨
- [ ] 5-3의 차단 채널·타인 메시지 시도가 의도대로 거부됨
