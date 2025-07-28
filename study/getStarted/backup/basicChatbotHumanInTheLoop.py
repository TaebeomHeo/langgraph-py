import os
import json
from typing import Annotated, Optional

from typing_extensions import TypedDict

from langchain_core.messages import ToolMessage, HumanMessage, AIMessage
from langchain_core.tools import tool
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langchain.chat_models import init_chat_model
from config import OLLAMA_BASE_URL, OLLAMA_MODEL, OPENAI_API_KEY
from langchain_tavily import TavilySearch
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command, interrupt
from langgraph.prebuilt import ToolNode, tools_condition

class State(TypedDict):
    # Messages have the type "list". The `add_messages` function
    # in the annotation defines how this state key should be updated
    # (in this case, it appends messages to the list, rather than overwriting them)
    messages: Annotated[list, add_messages]


graph_builder = StateGraph(State)

# Ollama 모델 초기화
llm = init_chat_model("openai:gpt-4o-mini")

@tool
def human_assistance(query: str) -> str:
    """
    Use this tool when you need human assistance or expert guidance.
    This will save the interrupt state and exit for human review.
    """
    import sys
    import sqlite3
    from datetime import datetime
    
    # interrupt 상태를 데이터베이스에 저장
    try:
        conn = sqlite3.connect('interrupt_state.db')
        cursor = conn.cursor()
        
        # interrupt_state 테이블 생성 (없으면)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS interrupt_state (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                thread_id TEXT,
                query TEXT,
                tool_name TEXT,
                timestamp TEXT,
                status TEXT DEFAULT 'pending',
                human_response TEXT
            )
        ''')
        
        # 현재 interrupt 상태 저장
        cursor.execute('''
            INSERT INTO interrupt_state (thread_id, query, tool_name, timestamp, status)
            VALUES (?, ?, ?, ?, ?)
        ''', ('default', query, 'human_assistance', datetime.now().isoformat(), 'pending'))
        
        conn.commit()
        conn.close()
        
        print(f"\n🔄 인간 전문가의 검토가 필요합니다: {query}")
        print("📋 interrupt 상태가 저장되었습니다.")
        print("👤 human_input_handler.py를 실행하여 검토를 진행해주세요.")
        print("🚪 메인 프로세스를 종료합니다...")
        
        # 프로세스 종료
        sys.exit(0)
        
    except Exception as e:
        return f"Error saving interrupt state: {str(e)}"

tool = TavilySearch(max_results=5)
tools = [tool, human_assistance]

# Modification: tell the LLM which tools it can call
llm_with_tools = llm.bind_tools(tools)

def validate_messages(messages):
    """메시지 상태를 검증하고 불완전한 도구 호출을 정리합니다."""
    if not messages:
        return messages
    
    cleaned_messages = []
    for i, message in enumerate(messages):
        # 도구 호출이 있지만 응답이 없는 경우 처리
        if (hasattr(message, 'tool_calls') and message.tool_calls and 
            i + 1 < len(messages) and 
            not any(hasattr(messages[i + 1], 'tool_call_id') for m in messages[i + 1:i + 2])):
            # 불완전한 도구 호출 메시지는 제거
            continue
        cleaned_messages.append(message)
    
    return cleaned_messages

def chatbot(state: State):
    """챗봇 노드 - 메시지 검증 후 LLM 호출"""
    try:
        # 메시지 상태 검증
        validated_messages = validate_messages(state["messages"])
        
        if not validated_messages:
            return {"messages": [AIMessage(content="죄송합니다. 메시지를 처리할 수 없습니다. 다시 시도해주세요.")]}
        
        # LLM 호출
        message = llm_with_tools.invoke(validated_messages)
        
        # 도구 호출이 1개 이하인지 확인 (Human-in-the-Loop를 위해)
        if hasattr(message, 'tool_calls') and len(message.tool_calls) > 1:
            # 여러 도구 호출이 있는 경우 첫 번째만 유지
            message.tool_calls = [message.tool_calls[0]]
        
        return {"messages": [message]}
    
    except Exception as e:
        print(f"❌ 챗봇 처리 중 오류 발생: {e}")
        return {"messages": [AIMessage(content="죄송합니다. 처리 중 오류가 발생했습니다. 다시 시도해주세요.")]}

class CustomToolNode:
    """도구 실행을 처리하는 커스텀 노드"""
    
    def __init__(self, tools: list):
        self.tools_by_name = {tool.name: tool for tool in tools}
    
    def __call__(self, state: State):
        try:
            messages = state.get("messages", [])
            if not messages:
                raise ValueError("메시지가 없습니다.")
            
            last_message = messages[-1]
            if not hasattr(last_message, 'tool_calls') or not last_message.tool_calls:
                return {"messages": []}
            
            tool_messages = []
            for tool_call in last_message.tool_calls:
                try:
                    tool_name = tool_call["name"]
                    tool_args = tool_call["args"]
                    
                    if tool_name not in self.tools_by_name:
                        raise ValueError(f"알 수 없는 도구: {tool_name}")
                    
                    # 도구 실행
                    if tool_name == "human_assistance":
                        print("🔄 Human-in-the-Loop 모드로 전환...")
                    
                    tool_result = self.tools_by_name[tool_name].invoke(tool_args)
                    
                    # interrupt가 반환된 경우 그대로 전달
                    if isinstance(tool_result, Command):
                        return tool_result
                    elif hasattr(tool_result, 'value'):  # Interrupt 객체 처리
                        # Interrupt 객체에서 Command 추출
                        interrupt_data = tool_result.value
                        if isinstance(interrupt_data, dict):
                            return Command(
                                type="interrupt",
                                data=interrupt_data,
                                resumable=True
                            )
                    elif hasattr(tool_result, '__iter__') and len(tool_result) == 1:
                        # Interrupt가 튜플로 반환되는 경우 처리
                        interrupt_obj = tool_result[0]
                        if hasattr(interrupt_obj, 'value'):
                            interrupt_data = interrupt_obj.value
                            if isinstance(interrupt_data, dict):
                                return Command(
                                    type="interrupt",
                                    data=interrupt_data,
                                    resumable=True
                                )
                    
                    # 도구 결과를 메시지로 변환
                    tool_message = ToolMessage(
                        content=str(tool_result),
                        name=tool_name,
                        tool_call_id=tool_call["id"]
                    )
                    tool_messages.append(tool_message)
                    
                except Exception as e:
                    print(f"❌ 도구 '{tool_name}' 실행 중 오류: {e}")
                    # 오류 메시지 생성
                    error_message = ToolMessage(
                        content=f"도구 실행 중 오류가 발생했습니다: {str(e)}",
                        name=tool_name,
                        tool_call_id=tool_call["id"]
                    )
                    tool_messages.append(error_message)
            
            return {"messages": tool_messages}
            
        except Exception as e:
            print(f"❌ 도구 노드 처리 중 오류: {e}")
            return {"messages": [ToolMessage(content=f"도구 처리 중 오류: {str(e)}")]}

tool_node = CustomToolNode(tools=tools)

def route_tools(state: State):
    """도구 호출 여부에 따라 라우팅 결정"""
    try:
        if isinstance(state, list):
            messages = state
        else:
            messages = state.get("messages", [])
        
        if not messages:
            return END
        
        last_message = messages[-1]
        
        # 도구 호출이 있는지 확인
        if (hasattr(last_message, 'tool_calls') and 
            last_message.tool_calls and 
            len(last_message.tool_calls) > 0):
            return "tools"
        
        return END
        
    except Exception as e:
        print(f"❌ 라우팅 중 오류: {e}")
        return END

# 그래프 구성
graph_builder.add_node("chatbot", chatbot)
graph_builder.add_node("tools", tool_node)
graph_builder.add_conditional_edges(
    "chatbot",
    route_tools,
    {"tools": "tools", END: END}
)
graph_builder.add_edge(START, "chatbot")
graph_builder.add_edge("tools", "chatbot")

# SQLite 체크포인터 설정
from langgraph.checkpoint.sqlite import SqliteSaver
import sqlite3

# SQLite 연결 (check_same_thread=False로 스레드 안전성 확보)
# Note: check_same_thread=False is OK as the implementation uses a lock
# to ensure thread safety.
conn = sqlite3.connect("./chatbot.db", check_same_thread=False)
memory = SqliteSaver(conn)

graph = graph_builder.compile(checkpointer=memory)

def stream_graph_updates(user_input: str, thread_id: str = "default"):
    """그래프 실행 및 결과 처리 - interrupt/Command 패턴 지원"""
    try:
        final_messages = None
        tool_used = False
        
        # 사용자 메시지 생성
        user_message = HumanMessage(content=user_input)
        
        for event in graph.stream(
            {"messages": [user_message]},
            config={"configurable": {"thread_id": thread_id}}
        ):
            # 각 노드의 결과를 확인
            for node_name, node_result in event.items():
                # interrupt/Command 처리
                if isinstance(node_result, Command):
                    if node_result.type == "interrupt":
                        print(f"\n🔄 AI가 사람의 입력을 기다립니다!")
                        print(f"질문: {node_result.data.get('query', 'Unknown')}")
                        print(f"스레드 ID: {thread_id}")
                        print("💡 별도의 프로그램에서 human_input_handler.py를 실행하여 답변을 입력하세요.")
                        return {
                            "status": "interrupted",
                            "command": node_result,
                            "thread_id": thread_id,
                            "data": node_result.data
                        }
                    else:
                        print(f"⚠️ 예상치 못한 Command 타입: {node_result.type}")
                        continue
                
                if "messages" in node_result:
                    final_messages = node_result["messages"]
                    # 도구 노드가 실행되었는지 확인
                    if node_name == "tools":
                        tool_used = True
                        print("🔍 도구를 사용하여 정보를 검색 중...")
        
        # 최종 결과에서 어시스턴트 메시지만 찾아서 출력
        if final_messages:
            # 마지막에서부터 어시스턴트 메시지를 찾음
            for message in reversed(final_messages):
                if hasattr(message, 'role') and message.role == 'assistant':
                    print("Assistant:", message.content)
                    return {"status": "completed", "messages": final_messages}
                elif hasattr(message, 'type') and message.type == 'ai':
                    print("Assistant:", message.content)
                    return {"status": "completed", "messages": final_messages}
            # 어시스턴트 메시지를 찾지 못한 경우 마지막 메시지 출력
            if final_messages:
                print("Assistant:", final_messages[-1].content)
                return {"status": "completed", "messages": final_messages}
        else:
            print("Assistant: 응답을 생성할 수 없습니다.")
            return {"status": "error", "message": "응답을 생성할 수 없습니다."}
            
    except Exception as e:
        print(f"❌ 그래프 실행 중 오류: {e}")
        print("Assistant: 죄송합니다. 처리 중 오류가 발생했습니다.")
        return {"status": "error", "message": str(e)}

def show_conversation_history(thread_id: str = "default"):
    """현재 스레드의 대화 기록을 보여줍니다."""
    try:
        # 메모리에서 현재 스레드의 상태를 가져옴
        config = {"configurable": {"thread_id": thread_id}}
        current_state = graph.get_state(config)
        
        if current_state and current_state.values.get("messages"):
            messages = validate_messages(current_state.values["messages"])
            
            if messages:
                print("\n📚 대화 기록:")
                print("-" * 50)
                for i, message in enumerate(messages, 1):
                    if hasattr(message, 'role'):
                        role = message.role
                        content = message.content
                    elif hasattr(message, 'type'):
                        role = message.type
                        content = message.content
                    else:
                        role = "unknown"
                        content = str(message)
                    
                    # 내용이 너무 길면 잘라서 표시
                    if len(content) > 100:
                        content = content[:100] + "..."
                    
                    print(f"{i}. {role.capitalize()}: {content}")
                print("-" * 50)
            else:
                print("📚 유효한 대화 기록이 없습니다.")
        else:
            print("📚 아직 대화 기록이 없습니다.")
    except Exception as e:
        print(f"❌ 대화 기록을 불러오는 중 오류가 발생했습니다: {e}")

def clear_memory(thread_id: str = "default"):
    """특정 스레드의 메모리를 초기화합니다."""
    try:
        config = {"configurable": {"thread_id": thread_id}}
        graph.get_state(config).delete()
        print(f"✅ 스레드 '{thread_id}'의 메모리가 초기화되었습니다.")
    except Exception as e:
        print(f"❌ 메모리 초기화 중 오류가 발생했습니다: {e}")

def get_thread_info(thread_id: str = "default"):
    """현재 스레드의 정보를 보여줍니다."""
    try:
        config = {"configurable": {"thread_id": thread_id}}
        current_state = graph.get_state(config)
        
        next_node = getattr(current_state, 'next', None)
        if current_state and current_state.values.get("messages"):
            message_count = len(current_state.values["messages"])
            print(f"📊 스레드 '{thread_id}' 정보:")
            print(f"   - 메시지 수: {message_count}")
            print(f"   - 메모리 사용: 활성 (SQLite)")
            print(f"   - 다음 노드(next): {next_node}")
        else:
            print(f"📊 스레드 '{thread_id}' 정보:")
            print(f"   - 메시지 수: 0")
            print(f"   - 메모리 사용: 비활성 (SQLite)")
            print(f"   - 다음 노드(next): {next_node}")
    except Exception as e:
        print(f"❌ 스레드 정보 조회 중 오류: {e}")

def resume_from_interrupt(thread_id: str, human_response: str):
    """interrupt 상태에서 human input으로 재개"""
    try:
        # ToolMessage로 human response를 추가
        tool_message = ToolMessage(
            content=human_response,
            name="human_assistance",
            tool_call_id="resume"
        )
        
        # 그래프 재실행
        for event in graph.stream(
            {"messages": [tool_message]},
            config={"configurable": {"thread_id": thread_id}}
        ):
            for node_name, node_result in event.items():
                if isinstance(node_result, Command):
                    if node_result.type == "interrupt":
                        print(f"🔄 또 다른 human input이 필요합니다: {node_result.data.get('query', 'Unknown')}")
                        return {"status": "interrupted", "command": node_result}
                
                if "messages" in node_result:
                    final_messages = node_result["messages"]
                    for message in reversed(final_messages):
                        if hasattr(message, 'role') and message.role == 'assistant':
                            print("Assistant:", message.content)
                            return {"status": "completed", "messages": final_messages}
                        elif hasattr(message, 'type') and message.type == 'ai':
                            print("Assistant:", message.content)
                            return {"status": "completed", "messages": final_messages}
        
        return {"status": "completed"}
        
    except Exception as e:
        print(f"❌ interrupt 재개 중 오류: {e}")
        return {"status": "error", "message": str(e)}

print("🤖 Human-in-the-Loop 챗봇이 시작되었습니다! (interrupt/Command 패턴)")
print("✨ 기능:")
print("   - 도구 사용 (웹 검색)")
print("   - Human-in-the-Loop (interrupt/Command 패턴)")
print("   - SQLite 외부 메모리 저장")
print("   - 대화 기록 저장")
print("   - 메모리 관리")
print("\n📋 명령어:")
print("- 'history': 대화 기록 보기")
print("- 'clear': 메모리 초기화")
print("- 'info': 스레드 정보 보기")
print("- 'quit', 'exit', 'q': 종료")
print("- 'help': 도움말 보기")

def show_help():
    """도움말을 표시합니다."""
    print("\n📖 도움말:")
    print("1. 일반 대화: 그냥 메시지를 입력하세요")
    print("2. 도구 사용: AI가 필요시 자동으로 웹 검색을 수행합니다")
    print("3. Human-in-the-Loop: AI가 도움이 필요하면 interrupt가 발생합니다")
    print("4. interrupt 발생 시: human_input_handler.py를 실행하여 답변을 입력하세요")
    print("5. 대화 기록: 'history' 명령어로 이전 대화를 확인할 수 있습니다")
    print("6. 메모리 관리: 'clear' 명령어로 대화 기록을 초기화할 수 있습니다")

while True:
    try:
        user_input = input("\nUser: ").strip()
        
        if not user_input:
            continue
            
        if user_input.lower() in ["quit", "exit", "q"]:
            print("👋 안녕히 가세요!")
            break
        elif user_input.lower() == "history":
            show_conversation_history()
        elif user_input.lower() == "clear":
            clear_memory()
        elif user_input.lower() == "info":
            get_thread_info()
        elif user_input.lower() == "help":
            show_help()
        else:
            result = stream_graph_updates(user_input)
            if result and result.get("status") == "interrupted":
                print(f"\n⏸️ 대화가 중단되었습니다. human_input_handler.py를 실행하여 답변을 입력하세요.")
                print(f"스레드 ID: {result.get('thread_id')}")
            
    except KeyboardInterrupt:
        print("\n👋 프로그램이 중단되었습니다.")
        break
    except Exception as e:
        print(f"❌ 예상치 못한 오류가 발생했습니다: {e}")
        print("프로그램을 다시 시작해주세요.")
        break
