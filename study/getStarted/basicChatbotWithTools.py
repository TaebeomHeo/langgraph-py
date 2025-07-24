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



class State(TypedDict):
    # Messages have the type "list". The `add_messages` function
    # in the annotation defines how this state key should be updated
    # (in this case, it appends messages to the list, rather than overwriting them)
    messages: Annotated[list, add_messages]


graph_builder = StateGraph(State)

# Ollama 모델 초기화
llm = init_chat_model("openai:gpt-4o-mini")

tool = TavilySearch(max_results=2)
tools = [tool]
# tool.invoke("What's a 'node' in LangGraph?")

# Modification: tell the LLM which tools it can call
# highlight-next-line
llm_with_tools = llm.bind_tools(tools)

def chatbot(state: State):
    return {"messages": [llm_with_tools.invoke(state["messages"])]}

class BasicToolNode:
    """A node that runs the tools requested in the last AIMessage."""

    def __init__(self, tools: list) -> None:
        self.tools_by_name = {tool.name: tool for tool in tools}

    def __call__(self, inputs: dict):
        if messages := inputs.get("messages", []):
            message = messages[-1]
        else:
            raise ValueError("No message found in input")
        outputs = []
        for tool_call in message.tool_calls:
            tool_result = self.tools_by_name[tool_call["name"]].invoke(
                tool_call["args"]
            )
            outputs.append(
                ToolMessage(
                    content=json.dumps(tool_result),
                    name=tool_call["name"],
                    tool_call_id=tool_call["id"],
                )
            )
        return {"messages": outputs}


tool_node = BasicToolNode(tools=[tool])

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

graph = graph_builder.compile()

def stream_graph_updates(user_input: str):
    # 그래프 실행 결과를 수집
    final_messages = None
    tool_used = False
    
    for event in graph.stream({"messages": [{"role": "user", "content": user_input}]}):
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


while True:
    try:
        user_input = input("User: ")
        if user_input.lower() in ["quit", "exit", "q"]:
            print("Goodbye!")
            break
        stream_graph_updates(user_input)
    except:
        # fallback if input() is not available
        user_input = "What do you know about LangGraph?"
        print("User: " + user_input)
        stream_graph_updates(user_input)
        break
