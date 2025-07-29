#!/usr/bin/env python3
"""
고도화된 멀티 스레드 Human-in-the-Loop 챗봇 (확장된 State)
- 사용자 정보 검증 및 수정
- 이름, 생년월일 정보 관리
- 멀티 스레드 interrupt 관리
- Thread 선택 및 전환
- State history 조회
- Pending thread 관리
"""

import os
import uuid
from datetime import datetime
from typing import Annotated, List, Dict, Optional
from typing_extensions import TypedDict

from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
from langchain_core.tools import tool, InjectedToolCallId
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langchain.chat_models import init_chat_model
from langchain_tavily import TavilySearch
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command, interrupt
from langgraph.prebuilt import ToolNode, tools_condition
import sqlite3
import config

class State(TypedDict):
    messages: Annotated[list, add_messages]
    name: str
    birthday: str
    birth_site: str

# LLM 초기화
if config.OPENAI_API_KEY:
    llm = init_chat_model(f"openai:{config.OPENAI_MODEL}")
    print(f"🔑 OpenAI 모델을 사용합니다: {config.OPENAI_MODEL}")
else:
    llm = init_chat_model(model=config.OLLAMA_MODEL, model_provider="ollama", base_url=config.OLLAMA_BASE_URL)
    print(f"🦙 Ollama 모델을 사용합니다: {config.OLLAMA_MODEL}")

@tool
def human_assistance(
    name: str, birthday: str, birth_site: str, tool_call_id: Annotated[str, InjectedToolCallId]
) -> str:
    """
    Human assistance 도구 - 실제 interrupt 발생
    """
    print(f"\n🤖 AI: 다음 정보를 검증해주세요.")
    print("=" * 60)
    print("📋 검증할 정보:")
    print(f"   이름: {name}")
    print(f"   생년월일: {birthday}")
    print(f"   출생지: {birth_site}")
    print("=" * 60)
    print("💡 응답 형식:")
    print("   - 정확한 경우: {\"correct\": \"y\"}")
    print("   - 수정이 필요한 경우: {\"correct\": \"n\", \"name\": \"새이름\", \"birthday\": \"새생년월일\", \"birth_site\": \"새출생지\"}")
    print("   - 변경 없는 필드는 생략 가능")
    print("=" * 60)
    
    # TypeScript 패턴: interrupt가 여기서 발생하고 실행 중단
    value = interrupt({
        "type": "human_assistance",
        "name": name,
        "birthday": birthday,
        "birth_site": birth_site,
        "timestamp": datetime.now().isoformat(),
        "status": "pending"
    })
    
    print(f"👤 인간이 입력한 값: {value}")
    
    # JSON 문자열을 파싱
    import json
    try:
        if isinstance(value, str):
            value = json.loads(value)
    except:
        # JSON 파싱 실패 시 기본값 사용
        value = {"correct": "n"}
    
    # If the information is correct, update the state as-is.
    if value.get("correct", "").lower().startswith("y"):
        verified_name = name
        verified_birthday = birthday
        verified_birth_site = birth_site
        response = "정보가 정확합니다."
    # Otherwise, receive information from the human reviewer.
    else:
        verified_name = value.get("name", name)
        verified_birthday = value.get("birthday", birthday)
        verified_birth_site = value.get("birth_site", birth_site)
        response = f"정보가 수정되었습니다: 이름={verified_name}, 생년월일={verified_birthday}, 출생지={verified_birth_site}"

    # State 업데이트를 위한 Command 반환
    return Command(update={
        "name": verified_name,
        "birthday": verified_birthday,
        "birth_site": verified_birth_site,
        "messages": [ToolMessage(response, tool_call_id=tool_call_id)]
    })

# 도구 설정
if config.TAVILY_API_KEY:
    tavily_search = TavilySearch(max_results=config.TAVILY_MAX_RESULTS)
    tools = [tavily_search, human_assistance]
    print("🔍 Tavily 검색 도구가 활성화되었습니다.")
else:
    tools = [human_assistance]
    print("⚠️ TAVILY_API_KEY가 설정되지 않아 검색 기능이 비활성화됩니다.")

llm_with_tools = llm.bind_tools(tools)

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

# 그래프 구성
graph_builder = StateGraph(State)
graph_builder.add_node("chatbot", chatbot)
graph_builder.add_node("tools", ToolNode(tools))

graph_builder.add_conditional_edges(
    "chatbot",
    tools_condition,
    {"tools": "tools", END: END}
)
graph_builder.add_edge(START, "chatbot")
graph_builder.add_edge("tools", "chatbot")

# SQLite 체크포인터 - Custom State DB 사용
conn = sqlite3.connect(config.CUSTOM_STATE_DB_PATH, check_same_thread=False)
memory = SqliteSaver(conn)

graph = graph_builder.compile(checkpointer=memory)

def generate_thread_id() -> str:
    """새로운 스레드 ID 생성"""
    return f"{config.THREAD_ID_PREFIX}_{uuid.uuid4().hex[:config.THREAD_ID_LENGTH]}_{datetime.now().strftime('%H%M%S')}"

# 전역 스레드 추적용
_active_threads = set()
_current_thread = None  # 현재 활성 스레드

def get_all_thread_states() -> List[Dict]:
    """
    모든 스레드 상태 조회 - TypeScript 패턴 따라 간단하게
    JavaScript 참조: getState(config) - config에는 thread_id만 필요
    """
    global _active_threads
    
    try:
        thread_states = []
        failed_threads = set()
        
        # TypeScript 패턴: 간단한 반복
        for thread_id in list(_active_threads):
            try:
                # 🎯 TypeScript 패턴: config에는 thread_id만
                thread_config = {"configurable": {"thread_id": thread_id}}
                snapshot = graph.get_state(thread_config)
                
                # 스레드에 실제 상태가 있는지 확인
                if not snapshot or not snapshot.values:
                    failed_threads.add(thread_id)
                    continue
                
                # 🎯 TypeScript 패턴: snapshot.next.length === 0 확인
                is_fresh_start = len(snapshot.next) == 0
                next_node_name = 'END' if is_fresh_start else snapshot.next[0]
                
                # 메시지 확인
                messages = snapshot.values.get("messages", [])
                last_message = messages[-1] if messages else None
                
                # State 정보 확인
                name = snapshot.values.get("name", "Unknown")
                birthday = snapshot.values.get("birthday", "Unknown")
                birth_site = snapshot.values.get("birth_site", "Unknown")
                
                # TypeScript 패턴: 간단한 toString() 처리
                timestamp = str(snapshot.created_at) if snapshot.created_at else "Unknown"
                
                thread_info = {
                    "thread_id": thread_id,
                    "is_interrupted": len(snapshot.next) > 0,  # pending 상태
                    "next_node": next_node_name,
                    "message_count": len(messages),
                    "last_message": getattr(last_message, 'content', 'No messages')[:80] if last_message else 'No messages',
                    "timestamp": timestamp,
                    "name": name,
                    "birthday": birthday,
                    "birth_site": birth_site
                }
                thread_states.append(thread_info)
                
            except Exception as e:
                print(f"⚠️ Thread {thread_id} 오류: {e}")
                failed_threads.add(thread_id)
                
        # 실패한 스레드 정리
        if failed_threads:
            _active_threads -= failed_threads
            save_active_threads()
                
        return thread_states
        
    except Exception as e:
        print(f"❌ 스레드 상태 조회 오류: {e}")
        return []

def get_pending_threads() -> List[Dict]:
    """Pending 상태인 스레드들만 조회 - TypeScript 패턴"""
    all_threads = get_all_thread_states()
    return [t for t in all_threads if t["is_interrupted"]]

def show_thread_history(thread_id: str) -> None:
    """
    특정 스레드의 대화 히스토리 조회 - 실제 대화 내용 중심
    """
    try:
        thread_config = {"configurable": {"thread_id": thread_id}}
        
        print(f"\n=== 💬 Thread History: {thread_id} ===")
        
        # 모든 snapshot을 리스트로 수집 후 역순으로 정렬 (최신이 아래에)
        snapshots = list(graph.get_state_history(thread_config))
        if not snapshots:
            print("📭 No conversation history found.")
            return
        
        # 이전 메시지 수를 추적하여 새로운 메시지만 출력
        prev_message_count = 0
        step_count = 0
        
        for snapshot in reversed(snapshots):  # 시간순으로 출력
            if not snapshot.values:
                continue
                
            messages = snapshot.values.get("messages", [])
            current_count = len(messages)
            
            # 새로운 메시지가 추가된 경우에만 출력
            if current_count > prev_message_count:
                step_count += 1
                
                # 시간 정보 (간단히)
                if snapshot.created_at:
                    time_str = str(snapshot.created_at)[:19].replace('T', ' ')
                    print(f"\n--- Step {step_count} ({time_str}) ---")
                else:
                    print(f"\n--- Step {step_count} ---")
                
                # State 정보 표시
                name = snapshot.values.get("name", "Unknown")
                birthday = snapshot.values.get("birthday", "Unknown")
                birth_site = snapshot.values.get("birth_site", "Unknown")
                print(f"📋 State: name='{name}', birthday='{birthday}', birth_site='{birth_site}'")
                
                # 새로 추가된 메시지들만 출력
                new_messages = messages[prev_message_count:]
                for msg in new_messages:
                    if hasattr(msg, 'content') and msg.content:
                        content = msg.content.strip()
                        if not content:
                            continue
                            
                        # 메시지 타입에 따라 출력
                        if hasattr(msg, '__class__'):
                            msg_type = msg.__class__.__name__
                            if msg_type == 'HumanMessage':
                                print(f"👤 User: {content}")
                            elif msg_type == 'AIMessage':
                                # tool_calls가 있는 경우 (도구 호출)
                                if hasattr(msg, 'tool_calls') and msg.tool_calls:
                                    tools = [tc.get('name', 'unknown') for tc in msg.tool_calls]
                                    print(f"🔧 AI: [도구 호출: {', '.join(tools)}]")
                                else:
                                    # 일반 AI 응답
                                    if len(content) > config.MESSAGE_PREVIEW_LENGTH * 4:  # 더 긴 미리보기
                                        content = content[:config.MESSAGE_PREVIEW_LENGTH * 4] + "..."
                                    print(f"🤖 AI: {content}")
                            elif msg_type == 'ToolMessage':
                                # 도구 실행 결과는 간단히
                                if hasattr(msg, 'name'):
                                    tool_name = msg.name
                                    preview = content[:config.MESSAGE_PREVIEW_LENGTH] + "..." if len(content) > config.MESSAGE_PREVIEW_LENGTH else content
                                    print(f"🔍 {tool_name}: {preview}")
                
                prev_message_count = current_count
        
        # 현재 상태 표시
        final_snapshot = snapshots[0]  # 가장 최신
        if final_snapshot.next:
            print(f"\n📋 Current Status: Pending (waiting for: {final_snapshot.next[0]})")
        else:
            print(f"\n✅ Thread Status: Complete")
        
        print("=" * 50)
        
    except Exception as e:
        print(f"❌ Error reading history: {e}")

def get_thread_context(thread_id: str) -> Dict:
    """스레드의 인간 검토 맥락 정보 추출"""
    try:
        thread_config = {"configurable": {"thread_id": thread_id}}
        snapshot = graph.get_state(thread_config)
        
        if not snapshot.values:
            return {"user_question": "No context", "ai_request": "No context", "summary": "No context", "name": "Unknown", "birthday": "Unknown", "birth_site": "Unknown"}
        
        messages = snapshot.values.get("messages", [])
        if not messages:
            return {"user_question": "No messages", "ai_request": "No messages", "summary": "No messages", "name": "Unknown", "birthday": "Unknown", "birth_site": "Unknown"}
        
        # State 정보
        name = snapshot.values.get("name", "Unknown")
        birthday = snapshot.values.get("birthday", "Unknown")
        birth_site = snapshot.values.get("birth_site", "Unknown")
        
        # 최근 사용자 질문 찾기
        user_question = "No user question found"
        ai_request = "No AI request found"
        
        # 뒤에서부터 찾기 (최신부터)
        for msg in reversed(messages):
            if hasattr(msg, '__class__'):
                msg_type = msg.__class__.__name__
                content = getattr(msg, 'content', '')
                
                # 사용자의 마지막 질문
                if msg_type == 'HumanMessage' and user_question == "No user question found":
                    user_question = content[:100] + "..." if len(content) > 100 else content
                
                # AI의 human_assistance 도구 호출 찾기
                elif msg_type == 'AIMessage' and hasattr(msg, 'tool_calls') and msg.tool_calls:
                    for tool_call in msg.tool_calls:
                        if tool_call.get('name') == 'human_assistance':
                            args = tool_call.get('args', {})
                            name_arg = args.get('name', 'No name specified')
                            birthday_arg = args.get('birthday', 'No birthday specified')
                            birth_site_arg = args.get('birth_site', 'No birth_site specified')
                            ai_request = f"Verify: name='{name_arg}', birthday='{birthday_arg}', birth_site='{birth_site_arg}'"
                            break
        
        # 대화 요약 (최근 3개 메시지)
        recent_messages = messages[-3:] if len(messages) >= 3 else messages
        summary_parts = []
        for msg in recent_messages:
            if hasattr(msg, '__class__'):
                msg_type = msg.__class__.__name__
                content = getattr(msg, 'content', '')[:50]
                if msg_type == 'HumanMessage':
                    summary_parts.append(f"👤{content}")
                elif msg_type == 'AIMessage' and not hasattr(msg, 'tool_calls'):
                    summary_parts.append(f"🤖{content}")
        
        summary = " → ".join(summary_parts) if summary_parts else "No conversation summary"
        
        return {
            "user_question": user_question,
            "ai_request": ai_request, 
            "summary": summary,
            "name": name,
            "birthday": birthday,
            "birth_site": birth_site
        }
        
    except Exception as e:
        return {"user_question": f"Error: {e}", "ai_request": f"Error: {e}", "summary": f"Error: {e}", "name": "Error", "birthday": "Error", "birth_site": "Error"}

def select_thread_interactive() -> Optional[str]:
    """인터랙티브 스레드 선택 - 인간 검토 맥락과 함께"""
    global _active_threads
    
    pending_threads = get_pending_threads()
    
    if not pending_threads:
        print("No pending threads.")
        return None
    
    print(f"\n🔍 Pending Threads ({len(pending_threads)}):")
    print("=" * 70)
    
    for i, thread in enumerate(pending_threads, 1):
        context = get_thread_context(thread['thread_id'])
        
        print(f"{i}. 📧 {thread['thread_id']}")
        print(f"   📋 Status: Waiting for {thread['next_node']}")
        print(f"   📊 Messages: {thread['message_count']}")
        print(f"   👤 User Question: {context['user_question']}")
        print(f"   🤖 AI Needs Help: {context['ai_request']}")
        print(f"   📝 Current State: name='{context['name']}', birthday='{context['birthday']}', birth_site='{context['birth_site']}'")
        print(f"   💬 Recent: {context['summary']}")
        print("-" * 70)
    
    while True:
        try:
            choice = input(f"\nSelect (1-{len(pending_threads)}, 'h'+number for history, '0' cancel): ").strip()
            
            if choice == '0':
                return None
            elif choice.startswith('h') and len(choice) > 1:
                # 히스토리 보기
                try:
                    idx = int(choice[1:]) - 1
                    if 0 <= idx < len(pending_threads):
                        show_thread_history(pending_threads[idx]['thread_id'])
                    else:
                        print("Invalid number.")
                except ValueError:
                    print("Use format: h1, h2, etc.")
            else:
                # 스레드 선택
                idx = int(choice) - 1
                if 0 <= idx < len(pending_threads):
                    selected_thread = pending_threads[idx]['thread_id']
                    print(f"Selected: {selected_thread}")
                    return selected_thread
                else:
                    print("Invalid number.")
        except ValueError:
            print("Enter a valid number.")
        except KeyboardInterrupt:
            print("\nCancelled.")
            return None

def resume_thread(thread_id: str, user_input: str) -> bool:
    """특정 스레드를 재개 - TypeScript 패턴"""
    global _active_threads
    
    try:
        thread_config = {"configurable": {"thread_id": thread_id}}
        
        # 스레드를 활성 목록에 추가하고 저장
        _active_threads.add(thread_id)
        save_active_threads()
        
        print(f"Resuming thread '{thread_id}'...")
        print(f"Input: {user_input}")
        
        # human_assistance 도구 호출인 경우 입력 형식 안내
        snapshot = graph.get_state(thread_config)
        if snapshot and snapshot.next and "tools" in snapshot.next:
            print("\n💡 입력 형식 안내:")
            print("   - 정확한 경우: {\"correct\": \"y\"}")
            print("   - 수정이 필요한 경우: {\"correct\": \"n\", \"name\": \"새이름\", \"birthday\": \"새생년월일\", \"birth_site\": \"새출생지\"}")
            print("   - 변경 없는 필드는 생략 가능")
            print("=" * 50)
        
        # Command로 재개
        for chunk in graph.stream(
            Command(resume=user_input),
            thread_config
        ):
            for node_name, node_output in chunk.items():
                if node_name == "chatbot" and "messages" in node_output:
                    message = node_output["messages"][-1]
                    
                    # Tool calls가 있는 경우
                    if hasattr(message, 'tool_calls') and message.tool_calls:
                        print(f"🔧 도구 호출: {[tool.get('name', 'unknown') for tool in message.tool_calls]}")
                    # 일반 응답인 경우
                    elif hasattr(message, 'content') and message.content:
                        print(f"Assistant: {message.content}")
                        
                elif node_name == "tools" and "messages" in node_output:
                    # 도구 실행 결과 출력
                    tool_messages = node_output["messages"]
                    for tool_msg in tool_messages:
                        if hasattr(tool_msg, 'content'):
                            print(f"🔍 도구 결과: {tool_msg.content[:config.SEARCH_RESULT_PREVIEW_LENGTH]}...")
                    
        return True
        
    except Exception as e:
        print(f"❌ 스레드 재개 중 오류: {e}")
        return False

def start_new_conversation(user_input: str) -> str:
    """새로운 대화 시작 - TypeScript 패턴"""
    global _active_threads
    
    thread_id = generate_thread_id()
    thread_config = {"configurable": {"thread_id": thread_id}}
    
    # 새 스레드를 활성 목록에 추가하고 저장
    _active_threads.add(thread_id)
    save_active_threads()
    
    print(f"New thread '{thread_id}' started...")
    
    try:
        for chunk in graph.stream(
            {"messages": [HumanMessage(content=user_input)]},
            thread_config
        ):
            if config.SHOW_CHUNK_DEBUG:
                print(f"📦 [NEW] Debug - Chunk: {chunk}")
            
            for node_name, node_output in chunk.items():
                if node_name == "chatbot" and "messages" in node_output:
                    message = node_output["messages"][-1]
                    
                    # Tool calls가 있는 경우 (첫 번째 chatbot 실행)
                    if hasattr(message, 'tool_calls') and message.tool_calls:
                        print(f"🔧 도구 호출: {[tool.get('name', 'unknown') for tool in message.tool_calls]}")
                    # 일반 응답인 경우 (최종 AI 응답)
                    elif hasattr(message, 'content') and message.content:
                        print(f"Assistant: {message.content}")
                        
                elif node_name == "tools" and "messages" in node_output:
                    # 도구 실행 결과 출력
                    tool_messages = node_output["messages"]
                    for tool_msg in tool_messages:
                        if hasattr(tool_msg, 'content'):
                            print(f"🔍 검색 결과: {tool_msg.content[:config.SEARCH_RESULT_PREVIEW_LENGTH]}...")
                    
    except Exception as e:
        if "interrupt" in str(e).lower():
            print(f"🔄 인간 검토 단계로 넘겼습니다!")
            print(f"📋 Thread '{thread_id}'는 pending 상태가 되었습니다.")
            print("💡 'select' 명령어로 나중에 재개할 수 있습니다.")
            print("🆕 새로운 스레드에서 대화를 계속합니다.")
            
            # 현재 스레드 비활성화
            global _current_thread
            if _current_thread == thread_id:
                _current_thread = None
                
        else:
            print(f"❌ 오류: {e}")
            
    return thread_id

def is_thread_pending(thread_id: str) -> bool:
    """스레드가 pending 상태인지 확인"""
    try:
        thread_config = {"configurable": {"thread_id": thread_id}}
        snapshot = graph.get_state(thread_config)
        
        if snapshot and hasattr(snapshot, 'next') and snapshot.next:
            # next가 있으면 pending 상태
            return True
        return False
    except:
        return False

def continue_conversation(user_input: str, thread_id: str) -> str:
    """기존 스레드에서 대화 계속하기"""
    
    # 먼저 스레드가 pending 상태인지 확인
    if is_thread_pending(thread_id):
        print(f"⚠️ Thread '{thread_id}'는 pending 상태입니다.")
        print("💡 'select' 명령어로 재개하거나 새 스레드에서 시작하세요.")
        return None
    
    thread_config = {"configurable": {"thread_id": thread_id}}
    
    try:
        for chunk in graph.stream(
            {"messages": [HumanMessage(content=user_input)]},
            thread_config
        ):
            if config.SHOW_CHUNK_DEBUG:
                print(f"📦 [CONTINUE] Debug - Chunk: {chunk}")
            
            for node_name, node_output in chunk.items():
                if node_name == "chatbot" and "messages" in node_output:
                    message = node_output["messages"][-1]
                    
                    # Tool calls가 있는 경우
                    if hasattr(message, 'tool_calls') and message.tool_calls:
                        print(f"🔧 도구 호출: {[tool.get('name', 'unknown') for tool in message.tool_calls]}")
                    # 일반 응답인 경우
                    elif hasattr(message, 'content') and message.content:
                        print(f"Assistant: {message.content}")
                        
                elif node_name == "tools" and "messages" in node_output:
                    # 도구 실행 결과 출력
                    tool_messages = node_output["messages"]
                    for tool_msg in tool_messages:
                        if hasattr(tool_msg, 'content'):
                            print(f"🔍 검색 결과: {tool_msg.content[:config.SEARCH_RESULT_PREVIEW_LENGTH]}...")
                    
    except Exception as e:
        if "interrupt" in str(e).lower():
            print(f"🔄 인간 검토 단계로 넘겼습니다!")
            print(f"📋 Thread '{thread_id}'는 pending 상태가 되었습니다.")
            print("💡 'select' 명령어로 나중에 재개할 수 있습니다.")
            print("🆕 새로운 스레드에서 대화를 계속합니다.")
            
            # 현재 스레드 비활성화
            global _current_thread
            if _current_thread == thread_id:
                _current_thread = None
                
            return None  # interrupt 발생 시 현재 스레드 비활성화
        else:
            print(f"❌ 오류: {e}")
            
    return thread_id

def discover_existing_threads():
    """기존 스레드 발견 - SQL 완전 제거, 파일 기반 추적"""
    global _active_threads  # 🎯 전역 변수 명시적 선언
    
    try:
        import os
        import json
        
        # 스레드 추적 파일 경로
        threads_file = config.THREADS_PATH
        
        if os.path.exists(threads_file):
            print("📁 기존 스레드 추적 파일 발견.")
            try:
                with open(threads_file, 'r') as f:
                    saved_threads = json.load(f)
                    
                # 저장된 스레드들이 실제로 유효한지 확인
                valid_threads = set()
                for thread_id in saved_threads:
                    try:
                        thread_config = {"configurable": {"thread_id": thread_id}}
                        snapshot = graph.get_state(thread_config)
                        if snapshot and snapshot.values:  # 실제 상태가 있으면 유효
                            valid_threads.add(thread_id)
                    except:
                        pass  # 유효하지 않은 스레드는 무시
                        
                _active_threads.update(valid_threads)
                
                if valid_threads:
                    print(f"✅ {len(valid_threads)}개의 기존 스레드를 복원했습니다.")
                    # 유효한 스레드들로 파일 업데이트
                    save_active_threads()
                else:
                    print("📝 유효한 기존 스레드가 없습니다.")
                    
            except Exception as e:
                print(f"📝 스레드 추적 파일 읽기 실패: {e}")
        else:
            print("📝 새로운 세션입니다.")
                
    except Exception as e:
        print(f"⚠️ 기존 스레드 검색 중 오류 (무시): {e}")

def save_active_threads():
    """활성 스레드 목록을 파일에 저장"""
    global _active_threads  # 🎯 전역 변수 명시적 선언
    
    try:
        import json
        with open(config.THREADS_PATH, 'w') as f:
            json.dump(list(_active_threads), f)
    except Exception as e:
        pass  # 저장 실패는 치명적이지 않음

def clear_all_threads():
    """모든 스레드 삭제 - 추적 파일과 메모리 정리"""
    global _active_threads, _current_thread
    
    try:
        import os
        import json
        
        # 현재 스레드 초기화
        _current_thread = None
        
        # 메모리에서 활성 스레드 목록 정리
        thread_count = len(_active_threads)
        _active_threads.clear()
        
        # 스레드 추적 파일 삭제
        if os.path.exists(config.THREADS_PATH):
            os.remove(config.THREADS_PATH)
        
        # 메인 데이터베이스 파일 삭제
        deleted_db_files = []
        if os.path.exists(config.CUSTOM_STATE_DB_PATH):
            try:
                os.remove(config.CUSTOM_STATE_DB_PATH)
                deleted_db_files.append(os.path.basename(config.CUSTOM_STATE_DB_PATH))
            except:
                pass  # 삭제 실패는 무시
        
        # 추가 DB 파일들 삭제 (설정된 경우에만)
        for db_path in config.ADDITIONAL_DB_PATHS:
            if os.path.exists(db_path):
                try:
                    os.remove(db_path)
                    deleted_db_files.append(os.path.basename(db_path))
                except:
                    pass  # 삭제 실패는 무시
        
        print(f"✅ {thread_count}개의 스레드가 삭제되었습니다.")
        if deleted_db_files:
            print(f"📁 데이터베이스 파일도 삭제됨: {', '.join(deleted_db_files)}")
        print("🆕 새로운 대화를 시작할 수 있습니다.")
        
        return True
        
    except Exception as e:
        print(f"❌ 스레드 삭제 중 오류: {e}")
        return False

def main():
    """고도화된 메인 함수"""
    print("🚀 고도화된 멀티 스레드 Human-in-the-Loop 챗봇 (확장된 State)")
    print("✨ 사용자 정보 검증 및 수정, 이름/생년월일 관리")
    print("=" * 70)
    
    # 프롬프트 가이드 표시
    print("\n📋 🤖 이 봇은 사람이름을 매개로 해서 생년월일, 출생지 등을 검색하는 bot입니다.")
    print("💡 위 취지에 맞게 prompt를 날려주세요.")
    print("💡 예시: '김철수에 대해 알려줘', '박영희의 생년월일과 출생지를 찾아줘'")
    print("=" * 70)
    
    # API 키 상태 확인
    if not config.TAVILY_API_KEY:
        print("⚠️ 경고: TAVILY_API_KEY가 설정되지 않았습니다.")
        print("   검색 기능을 사용하려면 .env 파일에 TAVILY_API_KEY를 설정하세요.")
        print("   현재는 human_assistance 도구만 사용 가능합니다.")
        print()
    
    # 기존 스레드 발견 시도
    discover_existing_threads()
    
    # 시작 시 pending 스레드 확인
    pending_threads = get_pending_threads()
    if pending_threads:
        print(f"🔍 {len(pending_threads)}개의 pending 스레드를 발견했습니다!")
        
        choice = input("Pending 스레드를 처리하시겠습니까? (y/n): ").strip().lower()
        if choice == 'y':
            selected_thread = select_thread_interactive()
            if selected_thread:
                print("\n💡 입력 형식 안내:")
                print("   - 정확한 경우: {\"correct\": \"y\"}")
                print("   - 수정이 필요한 경우: {\"correct\": \"n\", \"name\": \"새이름\", \"birthday\": \"새생년월일\", \"birth_site\": \"새출생지\"}")
                print("   - 변경 없는 필드는 생략 가능")
                print("=" * 50)
                user_input = input("👤 Human Input: ").strip()
                if user_input:
                    resume_thread(selected_thread, user_input)
    
    print("\n📋 명령어:")
    print("- 일반 메시지: 현재 스레드에서 대화 계속 (없으면 새 스레드)")
    print("- 'new': 새 스레드 시작")
    print("- 'pending': Pending 스레드 목록 보기")
    print("- 'threads': 모든 스레드 목록 보기")
    print("- 'select': Pending 스레드 선택하여 재개")
    print("- 'history <thread_id>': 특정 스레드 히스토리 보기")
    print("- 'clear': 모든 스레드 삭제")
    print("- 'quit': 종료")
    
    global _current_thread
    
    while True:
        try:
            user_input = input("\n🎯 입력: ").strip()
            
            if user_input.lower() in ["quit", "exit", "q"]:
                print("👋 안녕히 가세요!")
                break
                
            elif user_input.lower() == "new":
                # 명시적으로 새 스레드 시작
                if user_input:
                    message = input("💬 새 스레드에서 시작할 메시지: ").strip()
                    if message:
                        _current_thread = start_new_conversation(message)
                        print(f"📍 현재 스레드: {_current_thread}")
                
            elif user_input.lower() == "pending":
                # Pending 스레드 목록 보기
                pending = get_pending_threads()
                if pending:
                    print(f"\nPending threads ({len(pending)}):")
                    for thread in pending:
                        print(f"- {thread['thread_id']}: {thread['last_message']}")
                        print(f"  State: name='{thread['name']}', birthday='{thread['birthday']}', birth_site='{thread['birth_site']}'")
                else:
                    print("No pending threads.")
                    
            elif user_input.lower() == "threads":
                # 모든 스레드 목록 보기
                all_threads = get_all_thread_states()
                if all_threads:
                    print(f"\nAll threads ({len(all_threads)}):")
                    for thread in all_threads:
                        status = "Pending" if thread["is_interrupted"] else "Complete"
                        print(f"- {thread['thread_id']}: {status} | {thread['message_count']} messages")
                        print(f"  State: name='{thread['name']}', birthday='{thread['birthday']}', birth_site='{thread['birth_site']}'")
                else:
                    print("No threads.")
                    
            elif user_input.lower() == "select":
                # Pending 스레드 선택하여 재개
                selected_thread = select_thread_interactive()
                if selected_thread:
                    print("\n💡 입력 형식 안내:")
                    print("   - 정확한 경우: {\"correct\": \"y\"}")
                    print("   - 수정이 필요한 경우: {\"correct\": \"n\", \"name\": \"새이름\", \"birthday\": \"새생년월일\", \"birth_site\": \"새출생지\"}")
                    print("   - 변경 없는 필드는 생략 가능")
                    print("=" * 50)
                    user_response = input("👤 Human Input: ").strip()
                    if user_response:
                        if resume_thread(selected_thread, user_response):
                            _current_thread = selected_thread
                        
            elif user_input.lower().startswith("history "):
                # 특정 스레드 히스토리 보기
                thread_id = user_input[8:].strip()
                if thread_id:
                    show_thread_history(thread_id)
                else:
                    print("❌ Thread ID를 입력하세요. 예: history thread_abc123")
                    
            elif user_input.lower() == "clear":
                # 모든 스레드 삭제
                confirm = input("⚠️ 모든 스레드를 삭제하시겠습니까? (y/N): ").strip().lower()
                if confirm in ['y', 'yes']:
                    if clear_all_threads():
                        print("🔄 모든 스레드가 삭제되었습니다. 새로운 시작!")
                else:
                    print("❌ 삭제가 취소되었습니다.")
                    
            else:
                # 일반 대화 - 현재 스레드에서 계속하거나 새 스레드 시작
                if user_input:
                    if _current_thread:
                        # 기존 스레드에서 대화 계속
                        result = continue_conversation(user_input, _current_thread)
                        if result is None:
                            # pending 스레드이거나 interrupt 발생 - 새 스레드에서 시작
                            print(config.NEW_THREAD_MESSAGE)
                            _current_thread = start_new_conversation(user_input)
                            print(f"📍 현재 스레드: {_current_thread}")
                        else:
                            print(f"📍 현재 스레드: {_current_thread}")
                    else:
                        # 첫 번째 메시지 또는 interrupt 후 - 새 스레드 시작
                        _current_thread = start_new_conversation(user_input)
                        print(f"📍 현재 스레드: {_current_thread}")
                    
        except KeyboardInterrupt:
            print("\n👋 프로그램 종료")
            break
        except Exception as e:
            print(f"❌ 예상치 못한 오류: {e}")
    
    # 프로그램 종료 시 스레드 목록 저장
    save_active_threads()
    print("💾 스레드 목록이 저장되었습니다.")

if __name__ == "__main__":
    main() 