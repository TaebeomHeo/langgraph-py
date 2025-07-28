# 🤖 Human-in-the-Loop 챗봇 (interrupt/Command 패턴)

이 프로젝트는 LangGraph의 interrupt/Command 패턴을 사용하여 Human-in-the-Loop 기능을 구현한 챗봇 시스템입니다.

## 📁 파일 구조

```
study/getStarted/
├── basicChatbotHumanInTheLoop.py    # 메인 챗봇 프로그램
├── human_input_handler.py           # Human input 처리 프로그램
├── chatbot.db                       # SQLite 데이터베이스 (자동 생성)
└── README_interrupt_pattern.md      # 이 파일
```

## 🚀 주요 기능

### 1. **interrupt/Command 패턴**
- AI가 도움이 필요할 때 대화를 중단(interrupt)하고 외부에서 human input을 받음
- 메모리 상태를 SQLite에 저장하여 다른 프로그램에서 접근 가능

### 2. **SQLite 외부 메모리**
- 대화 기록과 상태를 SQLite 파일에 저장
- 프로그램 재시작 후에도 대화 상태 유지
- 여러 프로그램에서 동시에 접근 가능

### 3. **분리된 Human Input 처리**
- 메인 챗봇과 별도의 프로그램에서 human input 처리
- 웹 인터페이스나 다른 UI로 확장 가능

## 🛠️ 설치 및 실행

### 1. 메인 챗봇 실행
```bash
cd study/getStarted
python basicChatbotHumanInTheLoop.py
```

### 2. Human Input Handler 실행 (별도 터미널)
```bash
cd study/getStarted
python human_input_handler.py
```

## 📖 사용법

### 1. 일반 대화
```
User: 안녕하세요
Assistant: 안녕하세요! 무엇을 도와드릴까요?
```

### 2. 도구 사용 (웹 검색)
```
User: LangGraph에 대해 알려주세요
🔍 도구를 사용하여 정보를 검색 중...
Assistant: LangGraph는 LangChain에서 제공하는...
```

### 3. Human-in-the-Loop (interrupt 발생)
```
User: AI 에이전트 개발에 대한 전문가 조언이 필요해요
🔄 AI가 사람의 입력을 기다립니다!
질문: AI 에이전트 개발에 대한 전문가 조언이 필요합니다.
스레드 ID: default
💡 별도의 프로그램에서 human_input_handler.py를 실행하여 답변을 입력하세요.

⏸️ 대화가 중단되었습니다. human_input_handler.py를 실행하여 답변을 입력하세요.
스레드 ID: default
```

### 4. Human Input Handler에서 답변 입력
```
🤖 Human Input Handler
==================================================
interrupt 상태에서 human input을 처리하는 프로그램입니다.

📋 메뉴:
1. interrupt 스레드 목록 보기
2. 특정 스레드에 답변 입력
3. 스레드 정보 보기
4. 대화 기록 보기
5. 도움말
6. 종료

선택하세요 (1-6): 2
스레드 ID를 입력하세요: default

🤖 AI 질문: AI 에이전트 개발에 대한 전문가 조언이 필요합니다.
📅 시간: 2024-01-15T10:30:00

💬 답변을 입력하세요: AI 에이전트 개발 시에는 다음 사항들을 고려해야 합니다...
🔄 스레드 'default'에서 대화를 재개합니다...
✅ 대화가 성공적으로 재개되었습니다!
```

## 🔧 명령어

### 메인 챗봇 명령어
- `history`: 대화 기록 보기
- `clear`: 메모리 초기화
- `info`: 스레드 정보 보기
- `help`: 도움말 보기
- `quit`, `exit`, `q`: 종료

### Human Input Handler 명령어
- `1`: interrupt 스레드 목록 보기
- `2`: 특정 스레드에 답변 입력
- `3`: 스레드 정보 보기
- `4`: 대화 기록 보기
- `5`: 도움말
- `6`: 종료

## 🏗️ 아키텍처

### 1. **메인 챗봇 (basicChatbotHumanInTheLoop.py)**
```
사용자 입력 → 그래프 실행 → 도구 호출 → interrupt 발생 → 상태 저장
```

### 2. **Human Input Handler (human_input_handler.py)**
```
SQLite 상태 조회 → Human input 수집 → 메인 프로그램 재개 → 결과 반환
```

### 3. **SQLite 데이터베이스 (chatbot.db)**
```
- checkpoints 테이블: 대화 상태 저장
- messages 테이블: 대화 기록 저장
- thread_id로 스레드별 분리
```

## 🔄 동작 흐름

1. **사용자가 메인 챗봇에 질문**
2. **AI가 답변 생성 중 도구 호출 필요**
3. **human_assistance 도구 호출 시 interrupt 발생**
4. **대화 상태가 SQLite에 저장되고 프로그램 중단**
5. **사용자가 Human Input Handler 실행**
6. **Handler에서 SQLite 상태 조회 및 human input 수집**
7. **메인 프로그램 재개하여 대화 계속**

## 🎯 장점

### 1. **확장성**
- 웹 인터페이스, 모바일 앱 등 다양한 UI로 확장 가능
- 여러 사용자가 동시에 사용 가능

### 2. **안정성**
- 프로그램 중단 후에도 상태 유지
- 에러 발생 시 복구 가능

### 3. **유연성**
- Human input을 다양한 방식으로 수집 가능
- 비동기 처리 가능

### 4. **모니터링**
- SQLite를 통한 대화 상태 모니터링
- 로그 및 분석 가능

## 🚨 주의사항

1. **SQLite 파일 권한**: chatbot.db 파일에 읽기/쓰기 권한 필요
2. **동시 접근**: 여러 프로그램에서 동시 접근 시 주의
3. **메모리 관리**: 오래된 대화 기록 정리 필요
4. **에러 처리**: interrupt 재개 시 에러 상황 고려

## 🔮 향후 개선 방향

1. **웹 인터페이스**: Flask/FastAPI로 웹 UI 구현
2. **실시간 알림**: WebSocket으로 interrupt 알림
3. **사용자 관리**: 멀티 유저 지원
4. **대화 분석**: AI 분석 및 통계 기능
5. **플러그인 시스템**: 다양한 도구 추가 가능

## 📞 지원

문제가 발생하거나 개선 사항이 있으면 이슈를 등록해주세요! 