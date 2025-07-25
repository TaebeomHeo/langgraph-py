import os
import json
from typing import Annotated

from typing_extensions import TypedDict

from langchain_core.messages import ToolMessage
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langchain.chat_models import init_chat_model
from config import OLLAMA_BASE_URL, OLLAMA_MODEL, OPENAI_API_KEY
from langchain_tavily import TavilySearch
from langgraph.checkpoint.memory import MemorySaver
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
    Use this tool when you need human assistance.
    """
    human_response = interrupt({"query": query})
    return human_response["data"]

tool = TavilySearch(max_results=5)
tools = [tool, human_assistance]
# tool.invoke("What's a 'node' in LangGraph?")

# Modification: tell the LLM which tools it can call
# highlight-next-line
llm_with_tools = llm.bind_tools(tools)

def chatbot(state: State):
    # return {"messages": [llm_with_tools.invoke(state["messages"])]}
    message = llm_with_tools.invoke(state["messages"])
    # Because we will be interrupting during tool execution,
    # we disable parallel tool calling to avoid repeating any
    # tool invocations when we resume.
    assert len(message.tool_calls) <= 1
    return {"messages": [message]}


tool_node = ToolNode(tools=tools)

def route_tools(
    state: State,
):
    """
    Use in the conditional_edge to route to the ToolNode if the last message
    has tool calls. Otherwise, route to the end.
    """
    if isinstance(state, list):
        ai_message = state[-1]
    elif messages := state.get("messages", []):
        ai_message = messages[-1]
    else:
        raise ValueError(f"No messages found in input state to tool_edge: {state}")
    if hasattr(ai_message, "tool_calls") and len(ai_message.tool_calls) > 0:
        return "tools"
    return END


# The first argument is the unique node name
# The second argument is the function or object that will be called whenever
# the node is used.
# The `tools_condition` function returns "tools" if the chatbot asks to use a tool, and "END" if
# it is fine directly responding. This conditional routing defines the main agent loop.
graph_builder.add_node("chatbot", chatbot)
graph_builder.add_node("tools", tool_node)
graph_builder.add_conditional_edges(
    "chatbot",
    route_tools,
    # The following dictionary lets you tell the graph to interpret the condition's outputs as a specific node
    # It defaults to the identity function, but if you
    # want to use a node named something else apart from "tools",
    # You can update the value of the dictionary to something else
    # e.g., "tools": "my_tools"
    {"tools": "tools", END: END},
)
graph_builder.add_edge(START, "chatbot")
graph_builder.add_edge("tools", "chatbot")

# 메모리 저장소 설정
memory = MemorySaver()

graph = graph_builder.compile(checkpointer=memory)

def stream_graph_updates(user_input: str, thread_id: str = "default"):
    # 그래프 실행 결과를 수집
    final_messages = None
    tool_used = False
    
    for event in graph.stream(
        {"messages": [{"role": "user", "content": user_input}]},
        config={"configurable": {"thread_id": thread_id}}
    ):
        # 각 노드의 결과를 확인
        for node_name, node_result in event.items():
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
                return
            elif hasattr(message, 'type') and message.type == 'ai':
                print("Assistant:", message.content)
                return
        # 어시스턴트 메시지를 찾지 못한 경우 마지막 메시지 출력
        if final_messages:
            print("Assistant:", final_messages[-1].content)


# 대화 기록을 보여주는 함수
def show_conversation_history(thread_id: str = "default"):
    """현재 스레드의 대화 기록을 보여줍니다."""
    try:
        # 메모리에서 현재 스레드의 상태를 가져옴
        config = {"configurable": {"thread_id": thread_id}}
        current_state = graph.get_state(config)
        
        if current_state and current_state.values.get("messages"):
            print("\n📚 대화 기록:")
            print("-" * 50)
            for i, message in enumerate(current_state.values["messages"], 1):
                if hasattr(message, 'role'):
                    role = message.role
                    content = message.content
                elif hasattr(message, 'type'):
                    role = message.type
                    content = message.content
                else:
                    role = "unknown"
                    content = str(message)
                
                print(f"{i}. {role.capitalize()}: {content}")
            print("-" * 50)
        else:
            print("📚 아직 대화 기록이 없습니다.")
    except Exception as e:
        print(f"대화 기록을 불러오는 중 오류가 발생했습니다: {e}")

# 메모리 초기화 함수
def clear_memory(thread_id: str = "default"):
    """특정 스레드의 메모리를 초기화합니다."""
    try:
        config = {"configurable": {"thread_id": thread_id}}
        graph.get_state(config).delete()
        print(f"✅ 스레드 '{thread_id}'의 메모리가 초기화되었습니다.")
    except Exception as e:
        print(f"메모리 초기화 중 오류가 발생했습니다: {e}")

print("🤖 도구와 메모리가 있는 챗봇이 시작되었습니다!")
print("명령어:")
print("- 'history': 대화 기록 보기")
print("- 'clear': 메모리 초기화")
print("- 'quit', 'exit', 'q': 종료")

while True:
    try:
        user_input = input("\nUser: ")
        if user_input.lower() in ["quit", "exit", "q"]:
            print("Goodbye!")
            break
        elif user_input.lower() == "history":
            show_conversation_history()
        elif user_input.lower() == "clear":
            clear_memory()
        else:
            stream_graph_updates(user_input)
    except:
        # fallback if input() is not available
        user_input = "What do you know about LangGraph?"
        print("User: " + user_input)
        stream_graph_updates(user_input)
        break
