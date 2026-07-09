# 도움말 챗봇 병렬 작업 통합 메모

작성일: 2026-07-09

## 목적

다른 세션이 `web/index.html`, `web/app.js`, `web/styles.css`를 계속 수정하는 중에도 충돌을 줄이기 위해 도움말 챗봇 파일을 분리했다. LLM 연결을 위해 추천 API 서버에는 `/api/help-chat` 엔드포인트만 추가했다.

추가된 파일:

- `web/help-chatbot.html`
- `web/help-chatbot.css`
- `web/help-chatbot.js`
- `src/help_chatbot_service.py`
- `tests/test_help_chatbot_service.py`

## 현재 상태

`web/help-chatbot.html`은 독립 실행 가능한 도움말 페이지다. 오른쪽 고정 날개 배너를 누르면 챗봇 패널이 열린다.
접힌 날개 배너는 세로로 드래그해 위치를 옮길 수 있고, 열린 패널은 헤더의 이동 버튼으로 상하 이동할 수 있다. 팝업의 왼쪽/아래 테두리를 드래그하면 너비와 높이를 조절할 수 있다.

`web/index.html`에도 `help-chatbot.css`와 `help-chatbot.js`를 추가해 본 앱 오른쪽에 날개 배너형 챗봇이 자동으로 붙는다.

챗봇은 브라우저에서 직접 OpenAI 키를 다루지 않는다. 질문은 같은 서버의 `/api/help-chat`으로 보내고, 서버가 `OPENAI_API_KEY`를 사용해 LLM 답변을 생성한다. `.env` 또는 비밀값은 응답에 노출하지 않는다.

API 키가 없거나 정적 서버에서 열면 LLM 호출은 실패하거나 `disabled_no_key`가 되며, 화면은 안전한 기본 도움말로 대체한다.

답변 범위:

- 서비스 처음 사용법
- 점수와 등급 해석
- 휠체어 접근 확인
- 음식 제한 안내
- 실제 경로 보기
- 출처와 최신성
- 개인정보와 건강정보
- API 또는 화면 실패
- 운영자 검수 항목

## 본 앱에 붙이는 최소 변경

`web/index.html`에는 아래 두 줄이 추가되어 있다.

```html
<link rel="stylesheet" href="help-chatbot.css?v=20260710-8">
<script src="help-chatbot.js?v=20260710-8"></script>
```

위 방식은 기존 DOM을 수정하지 않아도 오른쪽 고정 날개 배너를 자동으로 만든다.

특정 위치에 삽입하고 싶으면 원하는 위치에 아래 컨테이너를 추가한다.

```html
<div data-help-chatbot data-help-chatbot-mode="wing"></div>
```

## 충돌 방지 기준

- 챗봇 후속 수정은 가능하면 `web/help-chatbot.*`와 `src/help_chatbot_service.py` 안에서 처리한다.
- 기존 추천 API나 라우트 API 응답 계약을 변경하지 않는다.
- OpenAI API 키는 서버 환경에서만 사용하고 프런트로 내려보내지 않는다.
- 개인정보, 진단명, 연락처, 병원명 입력을 유도하지 않는다.

## 확인 방법

LLM 답변까지 확인하려면 추천 API 서버로 실행한다.

```powershell
python scripts/serve_recommendation_api.py --port 8793 --generated-at 2026-07-09
```

브라우저 주소:

```text
http://127.0.0.1:8793/help-chatbot.html
```

정적 서버에서도 화면은 확인할 수 있지만 LLM 답변은 동작하지 않는다.
