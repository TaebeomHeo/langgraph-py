import os
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv()

# =============================================================================
# LLM 설정
# =============================================================================

# Ollama 설정
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gemma3:latest")

# OpenAI 설정 (필요시 사용)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

# =============================================================================
# 도구 설정
# =============================================================================

# Tavily 검색 설정
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")
TAVILY_MAX_RESULTS = int(os.getenv("TAVILY_MAX_RESULTS", "5"))

# =============================================================================
# 파일 및 디렉토리 설정
# =============================================================================

# 작업 디렉토리
WORKSPACE_DIR = os.getenv("WORKSPACE_DIR", "./")

# 데이터베이스 파일
DB_FILE = os.getenv("DB_FILE", "advanced_pattern.db")
DB_PATH = os.path.join(WORKSPACE_DIR, DB_FILE)

# Custom State 데이터베이스 파일
CUSTOM_STATE_DB_FILE = os.getenv("CUSTOM_STATE_DB_FILE", "custom_state.db")
CUSTOM_STATE_DB_PATH = os.path.join(WORKSPACE_DIR, CUSTOM_STATE_DB_FILE)

# 스레드 추적 파일
THREADS_FILE = os.getenv("THREADS_FILE", "active_threads.json")
THREADS_PATH = os.path.join(WORKSPACE_DIR, THREADS_FILE)

# Clear 시 삭제할 추가 DB 파일들 (실제 존재하는 파일만)
ADDITIONAL_DB_FILES = os.getenv("ADDITIONAL_DB_FILES", "").split(",") if os.getenv("ADDITIONAL_DB_FILES") else []
ADDITIONAL_DB_PATHS = [os.path.join(WORKSPACE_DIR, f.strip()) for f in ADDITIONAL_DB_FILES if f.strip()]

# =============================================================================
# UI 및 표시 설정
# =============================================================================

# 스레드 ID 생성 설정
THREAD_ID_PREFIX = os.getenv("THREAD_ID_PREFIX", "thread")
THREAD_ID_LENGTH = int(os.getenv("THREAD_ID_LENGTH", "8"))

# 표시 설정
SEARCH_RESULT_PREVIEW_LENGTH = int(os.getenv("SEARCH_RESULT_PREVIEW_LENGTH", "500"))
HISTORY_DISPLAY_LIMIT = int(os.getenv("HISTORY_DISPLAY_LIMIT", "10"))
MESSAGE_PREVIEW_LENGTH = int(os.getenv("MESSAGE_PREVIEW_LENGTH", "50"))

# 메시지 설정
INTERRUPT_MESSAGE = os.getenv("INTERRUPT_MESSAGE", "🔄 Human input이 필요합니다. 현재 스레드가 일시정지됩니다...")
NEW_THREAD_MESSAGE = os.getenv("NEW_THREAD_MESSAGE", "🆕 새로운 스레드에서 메시지를 처리합니다...")

# =============================================================================
# LangChain 추적 설정
# =============================================================================

LANGCHAIN_TRACING_V2 = os.getenv("LANGCHAIN_TRACING_V2", "false").lower() == "true"
LANGCHAIN_API_KEY = os.getenv("LANGCHAIN_API_KEY")

# =============================================================================
# 디버그 설정
# =============================================================================

DEBUG_MODE = os.getenv("DEBUG_MODE", "false").lower() == "true"
SHOW_CHUNK_DEBUG = os.getenv("SHOW_CHUNK_DEBUG", "false").lower() == "true" 