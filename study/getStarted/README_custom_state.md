# 🤖 Custom State Human-in-the-Loop 챗봇

## 📋 개요

`chatbotWithCustomState.py`는 LangGraph를 사용하여 구현된 고도화된 멀티 스레드 Human-in-the-Loop 챗봇입니다. 사용자 정보(이름, 생년월일, 출생지)를 검증하고 수정할 수 있는 기능을 제공합니다.

## ✨ 주요 기능

### 🏗️ **확장된 State 관리**

```python
class State(TypedDict):
    messages: Annotated[list, add_messages]
    name: str
    birthday: str
    birth_site: str
```

### 🔄 **Human-in-the-Loop 검증**

- AI가 검색한 정보를 사용자에게 검증 요청
- 사용자가 정보의 정확성을 확인하거나 수정 가능
- 수정된 정보가 State에 자동 반영

### 🧵 **멀티 스레드 관리**

- 여러 대화 세션을 동시에 관리
- Pending 스레드 추적 및 재개
- 스레드 히스토리 조회

### 💾 **데이터 지속성**

- SQLite 기반 상태 저장 (`custom_state.db`)
- 스레드 추적 파일 (`active_threads.json`)
- 프로그램 재시작 시 기존 스레드 복원

## 🚀 설치 및 설정

### 1. 환경변수 설정

```bash
# .env 파일 생성
OPENAI_API_KEY=your_openai_api_key
TAVILY_API_KEY=your_tavily_api_key
CUSTOM_STATE_DB_FILE=custom_state.db
```

### 2. 의존성 설치

```bash
pip install langgraph langchain-core langchain-tavily
```

### 3. 실행

```bash
python study/getStarted/chatbotWithCustomState.py
```

## 📖 사용법

### 기본 명령어

```
- 일반 메시지: 현재 스레드에서 대화 계속 (없으면 새 스레드)
- 'new': 새 스레드 시작
- 'pending': Pending 스레드 목록 보기
- 'threads': 모든 스레드 목록 보기
- 'select': Pending 스레드 선택하여 재개
- 'history <thread_id>': 특정 스레드 히스토리 보기
- 'clear': 모든 스레드 삭제
- 'quit': 종료
```

### 사용 예시

#### 1. 정보 검색 및 검증

```
🎯 입력: 이준석 국회의원 출생일, 출생지 검색
🤖 AI: 이준석 국회의원의 출생일과 출생지는 다음과 같습니다:
- 출생일: 1985년 3월 31일
- 출생지: 서울특별시

🎯 입력: 인간 검증
🔄 인간 검토 단계로 넘겼습니다!
📋 Thread 'thread_xxx'는 pending 상태가 되었습니다.
💡 'select' 명령어로 나중에 재개할 수 있습니다.
🆕 새로운 스레드에서 대화를 계속합니다.
```

#### 2. Pending 스레드 재개

```
🎯 입력: select
🔍 Pending Threads (1):
======================================================================
1. 📧 thread_xxx
   📋 Status: Waiting for tools
   📊 Messages: 6
   👤 User Question: 인간 검증
   🤖 AI Needs Help: Verify: name='이준석', birthday='1985-03-31', birth_site='서울특별시'
   📝 Current State: name='Unknown', birthday='Unknown', birth_site='Unknown'
   💬 Recent: 👤인간 검증
----------------------------------------------------------------------

Select (1-1, 'h'+number for history, '0' cancel): 1
Selected: thread_xxx

💡 입력 형식 안내:
   - 정확한 경우: {"correct": "y"}
   - 수정이 필요한 경우: {"correct": "n", "name": "새이름", "birthday": "새생년월일", "birth_site": "새출생지"}
   - 변경 없는 필드는 생략 가능
==================================================
👤 Human Input: {"correct":"y"}
```

#### 3. 정보 수정

```
👤 Human Input: {"correct":"n", "birth_site":"서울특별시 성동구"}
🤖 AI: 정보가 수정되었습니다: 이름=이준석, 생년월일=1985-03-31, 출생지=서울특별시 성동구
```

## 🔧 기술적 구현

### Human Assistance 도구

```python
@tool
def human_assistance(
    name: str, birthday: str, birth_site: str, tool_call_id: Annotated[str, InjectedToolCallId]
) -> str:
    """
    Human assistance 도구 - 실제 interrupt 발생
    """
    # 검증 정보 표시
    print(f"📋 검증할 정보:")
    print(f"   이름: {name}")
    print(f"   생년월일: {birthday}")
    print(f"   출생지: {birth_site}")

    # Interrupt 발생
    value = interrupt({
        "type": "human_assistance",
        "name": name,
        "birthday": birthday,
        "birth_site": birth_site,
        "timestamp": datetime.now().isoformat(),
        "status": "pending"
    })

    # JSON 파싱 및 State 업데이트
    return Command(update={
        "name": verified_name,
        "birthday": verified_birthday,
        "birth_site": verified_birth_site,
        "messages": [ToolMessage(response, tool_call_id=tool_call_id)]
    })
```

### State 정보 활용

```python
def chatbot(state: State):
    """챗봇 노드"""
    messages = state["messages"]

    # State 정보를 컨텍스트에 추가
    name = state.get("name", "Unknown")
    birthday = state.get("birthday", "Unknown")
    birth_site = state.get("birth_site", "Unknown")

    # State 정보가 유효한 경우 메시지에 추가
    if name != "Unknown" or birthday != "Unknown" or birth_site != "Unknown":
        context_message = f"현재 검증된 정보: 이름={name}, 생년월일={birthday}, 출생지={birth_site}"
        messages.append(HumanMessage(content=context_message))

    response = llm_with_tools.invoke(messages)
    return {"messages": [response]}
```

## 📊 데이터베이스 구조

### Custom State DB (`custom_state.db`)

- SQLite 기반 상태 저장
- 스레드별 State 정보 관리
- 메시지 히스토리 저장

### 스레드 추적 파일 (`active_threads.json`)

```json
["thread_abc123_123456", "thread_def456_234567"]
```

## 🎯 주요 개선사항

### 1. **사용자 친화적 검증 프로세스**

- JSON 형식 입력 안내
- 단계별 수정 가능
- 명확한 응답 메시지

### 2. **State 정보 활용**

- AI가 State 정보를 컨텍스트로 활용
- 검증된 정보를 기반으로 응답 생성
- State 업데이트 자동 반영

### 3. **멀티 스레드 관리**

- Pending 스레드 추적
- 스레드 히스토리 조회
- 인터랙티브 스레드 선택

### 4. **에러 처리 및 안정성**

- JSON 파싱 오류 처리
- 실패한 스레드 자동 정리
- 유효하지 않은 스레드 필터링

## 🔍 문제 해결

### Interrupt가 발생하지 않는 경우

1. `InjectedToolCallId` import 확인
2. `interrupt()` 함수 호출 확인
3. 복잡한 State 업데이트 제거

### State 업데이트가 반영되지 않는 경우

1. `Command(update=...)` 반환 확인
2. JSON 파싱 오류 확인
3. State 정보 컨텍스트 추가 확인

## 📈 향후 개선 방향

1. **더 많은 State 필드**: 직업, 학력, 경력 등 추가
2. **검증 히스토리**: 수정 이력 추적
3. **자동 검증**: 신뢰도 점수 기반 자동 검증
4. **UI 개선**: 웹 인터페이스 추가
5. **API 제공**: REST API 엔드포인트 추가

## 🤝 기여하기

이 프로젝트는 LangGraph의 Human-in-the-Loop 패턴을 학습하고 실험하기 위한 것입니다.

개선사항이나 버그 리포트는 이슈로 등록해주세요!

## 📄 라이선스

이 프로젝트는 학습 목적으로 제작되었습니다.
