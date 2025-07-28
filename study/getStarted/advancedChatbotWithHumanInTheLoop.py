#!/usr/bin/env python3
"""
고도화된 멀티 스레드 Human-in-the-Loop 챗봇
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

from langchain_core.messages import HumanMessage, AIMessage
from langchain_core.tools import tool
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langchain.chat_models import init_chat_model
from langchain_tavily import TavilySearch
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command, interrupt
from langgraph.prebuilt import ToolNode, tools_condition
import sqlite3
from config import OLLAMA_BASE_URL, OLLAMA_MODEL, OPENAI_API_KEY, TAVILY_API_KEY

class State(TypedDict):
    messages: Annotated[list, add_messages]

# LLM 초기화
if OPENAI_API_KEY:
    llm = init_chat_model("openai:gpt-4o-mini")
    print("🔑 OpenAI 모델을 사용합니다.")
else:
    llm = init_chat_model(model=OLLAMA_MODEL, model_provider="ollama", base_url=OLLAMA_BASE_URL)
    print(f"🦙 Ollama 모델을 사용합니다: {OLLAMA_MODEL}")

@tool
def human_assistance(query: str) -> str:
    """
    Human assistance 도구 - 실제 interrupt 발생
    """
    print(f"\n🤖 AI: {query}")
    print("🔄 Human input이 필요합니다. 현재 스레드가 일시정지됩니다...")
    
    # TypeScript 패턴: interrupt가 여기서 발생하고 실행 중단
    value = interrupt({
        "type": "human_assistance",
        "query": query,
        "timestamp": datetime.now().isoformat(),
        "status": "pending"
    })
    
    print(f"👤 인간이 입력한 값: {value}")
    return f"전문가 조언: {value}"

# 도구 설정
if TAVILY_API_KEY:
    tavily_search = TavilySearch(max_results=5)
    tools = [tavily_search, human_assistance]
    print("🔍 Tavily 검색 도구가 활성화되었습니다.")
else:
    tools = [human_assistance]
    print("⚠️ TAVILY_API_KEY가 설정되지 않아 검색 기능이 비활성화됩니다.")

llm_with_tools = llm.bind_tools(tools)

def chatbot(state: State):
    """챗봇 노드"""
    messages = state["messages"]
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

# SQLite 체크포인터
conn = sqlite3.connect("./advanced_pattern.db", check_same_thread=False)
memory = SqliteSaver(conn)

graph = graph_builder.compile(checkpointer=memory)

def generate_thread_id() -> str:
    """새로운 스레드 ID 생성"""
    return f"thread_{uuid.uuid4().hex[:8]}_{datetime.now().strftime('%H%M%S')}"

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
                config = {"configurable": {"thread_id": thread_id}}
                snapshot = graph.get_state(config)
                
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
                
                # TypeScript 패턴: 간단한 toString() 처리
                timestamp = str(snapshot.created_at) if snapshot.created_at else "Unknown"
                
                thread_info = {
                    "thread_id": thread_id,
                    "is_interrupted": len(snapshot.next) > 0,  # pending 상태
                    "next_node": next_node_name,
                    "message_count": len(messages),
                    "last_message": getattr(last_message, 'content', 'No messages')[:80] if last_message else 'No messages',
                    "timestamp": timestamp
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
    특정 스레드의 히스토리 조회 - TypeScript 패턴 따라 간단하게
    JavaScript 참조: printStateHistory() 함수
    """
    try:
        config = {"configurable": {"thread_id": thread_id}}
        
        print(f"\n=== State History for {thread_id} ===")
        
        # 🎯 TypeScript 패턴: 간단한 getStateHistory 사용
        history_count = 0
        for snapshot in graph.get_state_history(config):
            history_count += 1
            if history_count > 8:  # 최대 8개만 표시
                break
                
            # TypeScript 패턴: 간단한 정보 표시  
            timestamp = str(snapshot.created_at) if snapshot.created_at else "No timestamp"
            next_node = snapshot.next[0] if snapshot.next else "END"
            
            print(f"Timestamp: {timestamp}")
            print(f"Next Node: {next_node}")
            
            # 상태 간단히 표시
            if snapshot.values:
                messages = snapshot.values.get("messages", [])
                print(f"Messages: {len(messages)}")
                
                # 마지막 메시지만 간단히
                if messages:
                    last_msg = messages[-1]
                    content = getattr(last_msg, 'content', 'No content')
                    if len(content) > 50:
                        content = content[:50] + "..."
                    print(f"Last: {content}")
            
            print("-------------------\n")
            
        if history_count == 0:
            print("No history available.")
        
        print("===================")
        
    except Exception as e:
        print(f"Error: {e}")

def select_thread_interactive() -> Optional[str]:
    """인터랙티브 스레드 선택 - TypeScript 패턴으로 간단하게"""
    global _active_threads
    
    pending_threads = get_pending_threads()
    
    if not pending_threads:
        print("No pending threads.")
        return None
    
    print(f"\nPending Threads ({len(pending_threads)}):")
    print("=" * 50)
    
    for i, thread in enumerate(pending_threads, 1):
        print(f"{i}. {thread['thread_id']}")
        print(f"   Next: {thread['next_node']}")
        print(f"   Messages: {thread['message_count']}")
        print(f"   Last: {thread['last_message']}")
        print("-" * 30)
    
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
        config = {"configurable": {"thread_id": thread_id}}
        
        # 스레드를 활성 목록에 추가하고 저장
        _active_threads.add(thread_id)
        save_active_threads()
        
        print(f"Resuming thread '{thread_id}'...")
        print(f"Input: {user_input}")
        
        # Command로 재개
        for chunk in graph.stream(
            Command(resume=user_input),
            config
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
                            print(f"🔍 도구 결과: {tool_msg.content[:500]}...")
                    
        return True
        
    except Exception as e:
        print(f"❌ 스레드 재개 중 오류: {e}")
        return False

def start_new_conversation(user_input: str) -> str:
    """새로운 대화 시작 - TypeScript 패턴"""
    global _active_threads
    
    thread_id = generate_thread_id()
    config = {"configurable": {"thread_id": thread_id}}
    
    # 새 스레드를 활성 목록에 추가하고 저장
    _active_threads.add(thread_id)
    save_active_threads()
    
    print(f"New thread '{thread_id}' started...")
    
    try:
        for chunk in graph.stream(
            {"messages": [HumanMessage(content=user_input)]},
            config
        ):
            # print(f"📦 Debug - Chunk: {chunk}")  # 디버깅용
            
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
                            print(f"🔍 검색 결과: {tool_msg.content[:500]}...")  # 처음 500자만
                    
    except Exception as e:
        if "interrupt" in str(e).lower():
            print(f"🔄 Thread '{thread_id}'에서 interrupt 발생!")
            print("📋 이 스레드는 pending 상태가 되었습니다.")
            print("💡 'select' 명령어로 나중에 재개할 수 있습니다.")
        else:
            print(f"❌ 오류: {e}")
            
    return thread_id

def continue_conversation(user_input: str, thread_id: str) -> str:
    """기존 스레드에서 대화 계속하기"""
    config = {"configurable": {"thread_id": thread_id}}
    
    try:
        for chunk in graph.stream(
            {"messages": [HumanMessage(content=user_input)]},
            config
        ):
            # print(f"📦 Debug - Chunk: {chunk}")  # 디버깅용
            
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
                            print(f"🔍 검색 결과: {tool_msg.content[:500]}...")
                    
    except Exception as e:
        if "interrupt" in str(e).lower():
            print(f"🔄 Thread '{thread_id}'에서 interrupt 발생!")
            print("📋 이 스레드는 pending 상태가 되었습니다.")
            print("💡 'select' 명령어로 나중에 재개할 수 있습니다.")
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
        threads_file = "./active_threads.json"
        
        if os.path.exists(threads_file):
            print("📁 기존 스레드 추적 파일 발견.")
            try:
                with open(threads_file, 'r') as f:
                    saved_threads = json.load(f)
                    
                # 저장된 스레드들이 실제로 유효한지 확인
                valid_threads = set()
                for thread_id in saved_threads:
                    try:
                        config = {"configurable": {"thread_id": thread_id}}
                        snapshot = graph.get_state(config)
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
        with open("./active_threads.json", 'w') as f:
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
        threads_file = "./active_threads.json"
        if os.path.exists(threads_file):
            os.remove(threads_file)
        
        # SQLite 체크포인터 파일 삭제 (선택사항)
        db_files = ["chatbot.db", "memory.db"]
        deleted_db_files = []
        for db_file in db_files:
            if os.path.exists(db_file):
                try:
                    os.remove(db_file)
                    deleted_db_files.append(db_file)
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
    print("🚀 고도화된 멀티 스레드 Human-in-the-Loop 챗봇")
    print("✨ 멀티 스레드 관리, Interrupt 선택, State History")
    print("-" * 70)
    
    # API 키 상태 확인
    if not TAVILY_API_KEY:
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
                else:
                    print("No threads.")
                    
            elif user_input.lower() == "select":
                # Pending 스레드 선택하여 재개
                selected_thread = select_thread_interactive()
                if selected_thread:
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
                            # interrupt 발생 - 현재 스레드 비활성화
                            _current_thread = None
                            print("💭 다음 메시지는 새로운 스레드에서 시작됩니다.")
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