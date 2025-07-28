#!/usr/bin/env python3
"""
개선된 Human-in-the-Loop 챗봇
LangGraph의 공식 interrupt/Command 패턴 사용
"""

import os
from typing import Annotated
from typing_extensions import TypedDict

from langchain_core.messages import ToolMessage, HumanMessage, AIMessage
from langchain_core.tools import tool
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langchain.chat_models import init_chat_model
from langchain_tavily import TavilySearch
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command, interrupt
from langgraph.prebuilt import ToolNode, tools_condition
import sqlite3

class State(TypedDict):
    messages: Annotated[list, add_messages]

# LLM 초기화
llm = init_chat_model("openai:gpt-4o-mini")

@tool
def human_assistance(query: str) -> str:
    """
    인간 전문가의 도움이 필요할 때 사용하는 도구
    LangGraph의 공식 interrupt 패턴 사용
    """
    # 🎯 핵심: interrupt() 함수를 사용하여 그래프 실행 일시정지
    return interrupt({
        "type": "human_assistance",
        "query": query,
        "instruction": "전문가의 조언이나 도움이 필요합니다."
    })

# 도구 설정
tavily_search = TavilySearch(max_results=5)
tools = [tavily_search, human_assistance]

llm_with_tools = llm.bind_tools(tools)

def chatbot(state: State):
    """챗봇 노드 - 간단하고 명확한 구현"""
    messages = state["messages"]
    response = llm_with_tools.invoke(messages)
    return {"messages": [response]}

# 그래프 구성
graph_builder = StateGraph(State)
graph_builder.add_node("chatbot", chatbot)
graph_builder.add_node("tools", ToolNode(tools))

# 조건부 엣지 추가
graph_builder.add_conditional_edges(
    "chatbot",
    tools_condition,
    {"tools": "tools", END: END}
)
graph_builder.add_edge(START, "chatbot")
graph_builder.add_edge("tools", "chatbot")

# SQLite 체크포인터 설정
conn = sqlite3.connect("./improved_chatbot.db", check_same_thread=False)
memory = SqliteSaver(conn)

# 그래프 컴파일
graph = graph_builder.compile(checkpointer=memory)

def run_chatbot():
    """개선된 챗봇 실행"""
    print("🤖 개선된 Human-in-the-Loop 챗봇")
    print("✨ LangGraph 공식 interrupt/Command 패턴 사용")
    print("📝 명령어: 'quit'로 종료, 'history'로 대화 기록 확인")
    
    thread_id = "main_conversation"
    
    while True:
        try:
            user_input = input("\nUser: ").strip()
            
            if user_input.lower() in ["quit", "exit"]:
                print("👋 안녕히 가세요!")
                break
            elif user_input.lower() == "history":
                show_history(thread_id)
                continue
            
            # 사용자 메시지로 그래프 실행
            config = {"configurable": {"thread_id": thread_id}}
            
            try:
                # 그래프 스트리밍 실행
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
                            
            except Exception as e:
                # interrupt 발생 시 처리
                if "interrupt" in str(e).lower():
                    print("\n🔄 AI가 인간의 도움을 요청했습니다!")
                    
                    # 현재 상태에서 interrupt 정보 확인
                    current_state = graph.get_state(config)
                    if hasattr(current_state, 'tasks') and current_state.tasks:
                        task = current_state.tasks[0]
                        if hasattr(task, 'interrupts') and task.interrupts:
                            interrupt_data = task.interrupts[0].value
                            print(f"질문: {interrupt_data.get('query', 'Unknown')}")
                            
                            # 인간 입력 받기
                            human_response = input("👤 전문가 응답: ").strip()
                            
                            if human_response:
                                # Command를 사용하여 그래프 재개
                                result = graph.invoke(
                                    Command(resume=human_response),
                                    config=config
                                )
                                
                                # 최종 응답 출력
                                if "messages" in result:
                                    final_message = result["messages"][-1]
                                    if hasattr(final_message, 'content'):
                                        print(f"Assistant: {final_message.content}")
                            else:
                                print("❌ 빈 응답입니다.")
                    else:
                        print("❌ interrupt 정보를 찾을 수 없습니다.")
                else:
                    print(f"❌ 오류 발생: {e}")
                    
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
                if hasattr(msg, 'type'):
                    msg_type = msg.type
                elif hasattr(msg, 'role'):
                    msg_type = msg.role
                else:
                    msg_type = "unknown"
                
                content = getattr(msg, 'content', str(msg))
                if len(content) > 100:
                    content = content[:100] + "..."
                
                print(f"{i}. {msg_type.capitalize()}: {content}")
            print("-" * 50)
        else:
            print("📚 아직 대화 기록이 없습니다.")
    except Exception as e:
        print(f"❌ 대화 기록 조회 중 오류: {e}")

if __name__ == "__main__":
    run_chatbot() 