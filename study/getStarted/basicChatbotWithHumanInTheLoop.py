#!/usr/bin/env python3
"""
TypeScript 패턴을 따른 Python Human-in-the-Loop 구현
- SQL문 사용 안함
- interrupt() 함수 사용
- Command 패턴으로 재개
- 동일 프로세스 내에서 처리
"""

import os
from typing import Annotated
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
from config import OLLAMA_BASE_URL, OLLAMA_MODEL, OPENAI_API_KEY

class State(TypedDict):
    messages: Annotated[list, add_messages]

# LLM 초기화 - API 키가 있으면 OpenAI, 없으면 Ollama 사용
if OPENAI_API_KEY:
    llm = init_chat_model("openai:gpt-4o-mini")
    print("🔑 OpenAI 모델을 사용합니다.")
else:
    llm = init_chat_model(model=OLLAMA_MODEL, model_provider="ollama", base_url=OLLAMA_BASE_URL)
    print(f"🦙 Ollama 모델을 사용합니다: {OLLAMA_MODEL}")

@tool
def human_assistance(query: str) -> str:
    """
    TypeScript 패턴: interrupt() 함수 사용
    SQL문 없이 LangGraph 내장 메커니즘 활용
    """
    print(f"\n🤖 AI: {query}")
    print("🔄 인간의 입력을 기다립니다...")
    
    # 🎯 핵심: interrupt() 함수로 값을 전달하고 대기
    value = interrupt({
        "type": "human_assistance",
        "query": query,
        "timestamp": "지금"
    })
    
    print(f"👤 인간이 입력한 값: {value}")
    return f"전문가 조언: {value}"

# 도구 설정
tavily_search = TavilySearch(max_results=5)
tools = [tavily_search, human_assistance]

llm_with_tools = llm.bind_tools(tools)

def chatbot(state: State):
    """챗봇 노드 - 단순하고 명확"""
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

# SQLite 체크포인터 (SQL문 없이 단순히 저장용)
conn = sqlite3.connect("./ts_pattern.db", check_same_thread=False)
memory = SqliteSaver(conn)

graph = graph_builder.compile(checkpointer=memory)

def get_current_state(thread_id: str = "main"):
    """현재 상태 확인 - TypeScript의 getNextNode() 패턴"""
    config = {"configurable": {"thread_id": thread_id}}
    try:
        snapshot = graph.get_state(config)
        is_fresh_start = len(snapshot.next) == 0
        next_node = snapshot.next[0] if snapshot.next else None
        
        return {
            "is_fresh_start": is_fresh_start,
            "next_node": next_node,
            "values": snapshot.values,
            "config": config
        }
    except Exception as e:
        return {
            "is_fresh_start": True,
            "next_node": None,
            "values": None,
            "config": config
        }

def print_current_state(thread_id: str = "main"):
    """현재 상태 출력 - TypeScript 패턴"""
    state_info = get_current_state(thread_id)
    
    print("\n=== 현재 상태 ===")
    print(f"새로운 시작: {state_info['is_fresh_start']}")
    print(f"다음 노드: {state_info['next_node']}")
    if state_info['values'] and state_info['values'].get('messages'):
        msg_count = len(state_info['values']['messages'])
        print(f"메시지 수: {msg_count}")
    print("================\n")
    
    return state_info

def run_fresh_conversation(user_input: str, config: dict):
    """새로운 대화 시작 - TypeScript 패턴"""
    print("🆕 새로운 대화를 시작합니다...")
    
    try:
        for chunk in graph.stream(
            {"messages": [HumanMessage(content=user_input)]},
            config
        ):
            print("📦 Before interrupt chunk:", chunk)
            
            # 챗봇 응답이 있으면 출력
            for node_name, node_output in chunk.items():
                if node_name == "chatbot" and "messages" in node_output:
                    message = node_output["messages"][-1]
                    if hasattr(message, 'content') and not hasattr(message, 'tool_calls'):
                        print(f"Assistant: {message.content}")
                elif node_name == "tools":
                    print("🔍 도구를 실행합니다...")
                    
    except Exception as e:
        print(f"🔄 Interrupt 발생: {e}")
        print("인간의 입력이 필요합니다!")

def resume_conversation(user_input: str, config: dict):
    """대화 재개 - TypeScript의 Command 패턴"""
    print(f"🔄 사용자 입력으로 대화를 재개합니다: {user_input}")
    
    try:
        # 🎯 핵심: Command({resume: value})로 재개
        for chunk in graph.stream(
            Command(resume=user_input),
            config
        ):
            print("📦 After interrupt chunk:", chunk)
            
            # 최종 응답 출력
            for node_name, node_output in chunk.items():
                if node_name == "chatbot" and "messages" in node_output:
                    message = node_output["messages"][-1]
                    if hasattr(message, 'content'):
                        print(f"Assistant: {message.content}")
                elif node_name == "tools":
                    print("🔍 도구를 실행합니다...")
                    
    except Exception as e:
        print(f"❌ 재개 중 오류: {e}")

def main():
    """메인 함수 - TypeScript 패턴 완전 구현"""
    print("🤖 TypeScript 패턴 Human-in-the-Loop 챗봇")
    print("✨ interrupt() + Command 패턴 사용")
    print("📝 SQL문 없이 LangGraph 내장 메커니즘만 사용")
    print("-" * 60)
    
    thread_id = "main"
    
    while True:
        try:
            # 🔍 TypeScript 패턴: 현재 상태 확인
            state_info = print_current_state(thread_id)
            
            if state_info["is_fresh_start"]:
                # 🆕 새로운 대화
                user_input = input("User (새 대화): ").strip()
                if user_input.lower() in ["quit", "exit"]:
                    break
                    
                run_fresh_conversation(user_input, state_info["config"])
                
            else:
                # 🔄 interrupt에서 재개
                print("현재 interrupt 상태입니다.")
                user_input = input("👤 Human Input (재개): ").strip()
                if user_input.lower() in ["quit", "exit"]:
                    break
                    
                resume_conversation(user_input, state_info["config"])
                
        except KeyboardInterrupt:
            print("\n👋 프로그램 종료")
            break
        except Exception as e:
            print(f"❌ 오류: {e}")

if __name__ == "__main__":
    main() 