import os
import uuid
from typing import Annotated

from typing_extensions import TypedDict

from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langchain.chat_models import init_chat_model
from config import OLLAMA_BASE_URL, OLLAMA_MODEL, OPENAI_API_KEY
from langchain_tavily import TavilySearch
from langgraph.checkpoint.memory import InMemorySaver



class State(TypedDict):
    # Messages have the type "list". The `add_messages` function
    # in the annotation defines how this state key should be updated
    # (in this case, it appends messages to the list, rather than overwriting them)
    messages: Annotated[list, add_messages]


graph_builder = StateGraph(State)

# Ollama 모델 초기화
llm = init_chat_model(model=OLLAMA_MODEL, model_provider="ollama", base_url=OLLAMA_BASE_URL)

def chatbot(state: State):
    return {"messages": [llm.invoke(state["messages"])]}


# The first argument is the unique node name
# The second argument is the function or object that will be called whenever
# the node is used.
graph_builder.add_node("chatbot", chatbot)
graph_builder.add_edge(START, "chatbot")
graph_builder.add_edge("chatbot", END)

memory = InMemorySaver()

graph = graph_builder.compile(checkpointer=memory)

# 전역 변수로 현재 thread_id 저장
current_thread_id = None

def generate_thread_id():
    """고유한 thread_id를 생성합니다."""
    return str(uuid.uuid4())

def start_new_session():
    """새로운 대화 세션을 시작합니다."""
    global current_thread_id
    current_thread_id = generate_thread_id()
    print(f"🆔 새로운 대화 세션 시작 (Thread ID: {current_thread_id})")

def stream_graph_updates(user_input: str):
    global current_thread_id
    
    # thread_id가 없으면 새로운 세션 시작
    if current_thread_id is None:
        start_new_session()
    
    config = {"configurable": {"thread_id": current_thread_id}}
    
    for event in graph.stream({"messages": [{"role": "user", "content": user_input}]}, config=config):
        for value in event.values():
            print("Assistant:", value["messages"][-1].content)


while True:
    try:
        user_input = input("User: ")
        if user_input.lower() in ["quit", "exit", "q"]:
            print("Goodbye!")
            break
        elif user_input.lower() in ["new", "새로", "새세션"]:
            start_new_session()
            continue
        stream_graph_updates(user_input)
    except:
        # fallback if input() is not available
        user_input = "What do you know about LangGraph?"
        print("User: " + user_input)
        stream_graph_updates(user_input)
        break
