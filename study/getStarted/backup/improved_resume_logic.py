#!/usr/bin/env python3
"""
개선된 Human-in-the-Loop 챗봇 - 자동 재개 로직 포함
프로세스 시작 시 pending된 interrupt를 자동으로 확인하고 재개
"""

import os
import json
import sqlite3
from datetime import datetime
from typing import Annotated, Optional

from typing_extensions import TypedDict
from langchain_core.messages import ToolMessage, HumanMessage, AIMessage
from langchain_core.tools import tool
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langchain.chat_models import init_chat_model
from langchain_tavily import TavilySearch
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.prebuilt import ToolNode, tools_condition

class State(TypedDict):
    messages: Annotated[list, add_messages]

# LLM 초기화
llm = init_chat_model("openai:gpt-4o-mini")

@tool
def human_assistance(query: str) -> str:
    """
    인간 전문가의 도움이 필요할 때 사용하는 도구
    상태를 저장하고 프로세스를 종료하여 외부에서 처리되도록 함
    """
    import sys
    import sqlite3
    from datetime import datetime
    
    print(f"\n🔄 인간 전문가의 검토가 필요합니다: {query}")
    print("📋 interrupt 상태를 저장합니다...")
    
    try:
        # interrupt 상태를 데이터베이스에 저장
        conn = sqlite3.connect('interrupt_state.db')
        cursor = conn.cursor()
        
        # interrupt_state 테이블 생성
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS interrupt_state (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                thread_id TEXT,
                query TEXT,
                tool_name TEXT,
                timestamp TEXT,
                status TEXT DEFAULT 'pending',
                human_response TEXT,
                created_at TEXT
            )
        ''')
        
        # 현재 interrupt 상태 저장
        cursor.execute('''
            INSERT INTO interrupt_state (thread_id, query, tool_name, timestamp, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', ('default', query, 'human_assistance', datetime.now().isoformat(), 'pending', datetime.now().isoformat()))
        
        conn.commit()
        conn.close()
        
        print("✅ interrupt 상태가 저장되었습니다.")
        print("👤 human_input_handler.py를 실행하여 검토를 진행해주세요.")
        print("🚪 메인 프로세스를 종료합니다...")
        
        # 로깅: 어디서 pending되었는지 기록
        log_interrupt_event(query, 'pending')
        
        # 프로세스 종료
        sys.exit(0)
        
    except Exception as e:
        print(f"❌ interrupt 상태 저장 중 오류: {e}")
        return f"Error saving interrupt state: {str(e)}"

def log_interrupt_event(query: str, status: str, details: str = ""):
    """interrupt 이벤트를 로깅"""
    try:
        conn = sqlite3.connect('interrupt_state.db')
        cursor = conn.cursor()
        
        # 로그 테이블 생성
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS interrupt_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                thread_id TEXT,
                event_type TEXT,
                query TEXT,
                status TEXT,
                details TEXT
            )
        ''')
        
        # 로그 기록
        cursor.execute('''
            INSERT INTO interrupt_logs (timestamp, thread_id, event_type, query, status, details)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (datetime.now().isoformat(), 'default', 'interrupt', query, status, details))
        
        conn.commit()
        conn.close()
        
    except Exception as e:
        print(f"⚠️ 로깅 중 오류: {e}")

def check_pending_interrupts(thread_id: str = "default"):
    """프로세스 시작 시 pending된 interrupt가 있는지 확인"""
    try:
        conn = sqlite3.connect('interrupt_state.db')
        cursor = conn.cursor()
        
        # pending 상태인 interrupt 조회
        cursor.execute("""
            SELECT id, query, timestamp, human_response 
            FROM interrupt_state 
            WHERE thread_id = ? AND status = 'completed' AND human_response IS NOT NULL
            ORDER BY timestamp DESC
            LIMIT 1
        """, (thread_id,))
        
        result = cursor.fetchone()
        conn.close()
        
        if result:
            interrupt_id, query, timestamp, human_response = result
            print(f"\n🔄 이전에 완료된 interrupt를 발견했습니다!")
            print(f"📋 Query: {query}")
            print(f"💬 Human Response: {human_response}")
            print(f"⏰ Time: {timestamp}")
            
            # 로깅: 재개 이벤트 기록
            log_interrupt_event(query, 'resumed', f"Human response: {human_response}")
            
            # 해당 interrupt를 처리됨으로 표시
            mark_interrupt_processed(interrupt_id)
            
            return {
                'id': interrupt_id,
                'query': query, 
                'human_response': human_response,
                'timestamp': timestamp
            }
        
        return None
        
    except Exception as e:
        print(f"❌ pending interrupt 확인 중 오류: {e}")
        return None

def mark_interrupt_processed(interrupt_id: int):
    """interrupt를 처리됨으로 표시"""
    try:
        conn = sqlite3.connect('interrupt_state.db')
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE interrupt_state 
            SET status = 'processed', timestamp = ?
            WHERE id = ?
        """, (datetime.now().isoformat(), interrupt_id))
        
        conn.commit()
        conn.close()
        
    except Exception as e:
        print(f"❌ interrupt 처리 표시 중 오류: {e}")

def resume_with_human_response(human_response: str, thread_id: str = "default"):
    """human response로 대화를 재개"""
    try:
        config = {"configurable": {"thread_id": thread_id}}
        
        # ToolMessage로 human response를 추가
        tool_message = ToolMessage(
            content=human_response,
            name="human_assistance",
            tool_call_id="human_input"
        )
        
        print(f"🔄 Human response로 대화를 재개합니다...")
        print(f"💬 Response: {human_response}")
        
        # 그래프 실행
        for event in graph.stream(
            {"messages": [tool_message]},
            config=config
        ):
            for node_name, node_result in event.items():
                if "messages" in node_result:
                    final_messages = node_result["messages"]
                    # 마지막 AI 응답 출력
                    for message in reversed(final_messages):
                        if hasattr(message, 'type') and message.type == 'ai':
                            print(f"Assistant: {message.content}")
                            return True
                        elif hasattr(message, 'role') and message.role == 'assistant':
                            print(f"Assistant: {message.content}")
                            return True
        
        return True
        
    except Exception as e:
        print(f"❌ 재개 중 오류: {e}")
        return False

# 도구 설정
tavily_search = TavilySearch(max_results=5)
tools = [tavily_search, human_assistance]

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

# SQLite 체크포인터 설정
conn = sqlite3.connect("./chatbot.db", check_same_thread=False)
memory = SqliteSaver(conn)

graph = graph_builder.compile(checkpointer=memory)

def run_chatbot():
    """개선된 챗봇 실행 - 시작 시 pending 상태 확인"""
    print("🤖 개선된 Human-in-the-Loop 챗봇")
    print("✨ 자동 재개 로직 포함")
    print("-" * 50)
    
    thread_id = "default"
    
    # 🎯 핵심: 프로세스 시작 시 pending된 interrupt 확인
    print("🔍 이전 interrupt 상태를 확인합니다...")
    pending_interrupt = check_pending_interrupts(thread_id)
    
    if pending_interrupt:
        # 자동으로 human response로 재개
        success = resume_with_human_response(pending_interrupt['human_response'], thread_id)
        if success:
            print("✅ 이전 상태에서 성공적으로 재개되었습니다!")
        else:
            print("❌ 재개에 실패했습니다.")
    else:
        print("📝 새로운 대화를 시작합니다.")
    
    print("\n📋 명령어: 'quit'로 종료, 'history'로 대화 기록 확인, 'logs'로 interrupt 로그 확인")
    
    while True:
        try:
            user_input = input("\nUser: ").strip()
            
            if user_input.lower() in ["quit", "exit"]:
                print("👋 안녕히 가세요!")
                break
            elif user_input.lower() == "history":
                show_history(thread_id)
                continue
            elif user_input.lower() == "logs":
                show_interrupt_logs()
                continue
            
            # 사용자 메시지로 그래프 실행
            config = {"configurable": {"thread_id": thread_id}}
            
            for event in graph.stream(
                {"messages": [HumanMessage(content=user_input)]},
                config=config
            ):
                for node_name, node_output in event.items():
                    if node_name == "chatbot" and "messages" in node_output:
                        message = node_output["messages"][-1]
                        if hasattr(message, 'content') and not hasattr(message, 'tool_calls'):
                            print(f"Assistant: {message.content}")
                    elif node_name == "tools":
                        print("🔍 도구를 사용하여 정보를 검색 중...")
                        
        except KeyboardInterrupt:
            print("\n👋 프로그램이 중단되었습니다.")
            break
        except Exception as e:
            print(f"❌ 예상치 못한 오류: {e}")

def show_history(thread_id: str):
    """대화 기록 표시"""
    try:
        config = {"configurable": {"thread_id": thread_id}}
        state = graph.get_state(config)
        
        if state and state.values.get("messages"):
            messages = state.values["messages"]
            print(f"\n📚 대화 기록 (총 {len(messages)}개 메시지):")
            print("-" * 50)
            
            for i, msg in enumerate(messages, 1):
                msg_type = getattr(msg, 'type', getattr(msg, 'role', 'unknown'))
                content = getattr(msg, 'content', str(msg))
                if len(content) > 100:
                    content = content[:100] + "..."
                print(f"{i}. {msg_type.capitalize()}: {content}")
            print("-" * 50)
        else:
            print("📚 아직 대화 기록이 없습니다.")
    except Exception as e:
        print(f"❌ 대화 기록 조회 중 오류: {e}")

def show_interrupt_logs():
    """interrupt 로그 표시"""
    try:
        conn = sqlite3.connect('interrupt_state.db')
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT timestamp, event_type, query, status, details
            FROM interrupt_logs 
            ORDER BY timestamp DESC 
            LIMIT 10
        """)
        
        logs = cursor.fetchall()
        conn.close()
        
        if logs:
            print("\n📋 최근 Interrupt 로그 (최대 10개):")
            print("-" * 80)
            for log in logs:
                timestamp, event_type, query, status, details = log
                print(f"⏰ {timestamp}")
                print(f"📋 {event_type.upper()}: {query}")
                print(f"🔄 Status: {status}")
                if details:
                    print(f"💬 Details: {details}")
                print("-" * 40)
        else:
            print("📋 아직 interrupt 로그가 없습니다.")
            
    except Exception as e:
        print(f"❌ 로그 조회 중 오류: {e}")

if __name__ == "__main__":
    run_chatbot() 