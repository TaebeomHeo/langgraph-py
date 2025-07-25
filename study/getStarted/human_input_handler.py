#!/usr/bin/env python3
"""
Human Input Handler for LangGraph Chatbot
interrupt 상태에서 사용자 입력을 받아 메인 프로그램에 전달하는 프로그램
"""

import os
import sys
import json
import sqlite3
from typing import Optional, Dict, Any
from datetime import datetime

# 메인 프로그램의 함수들을 import하기 위한 경로 설정
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    from basicChatbotHumanInTheLoop import resume_from_interrupt, get_thread_info, show_conversation_history
except ImportError:
    print("❌ basicChatbotHumanInTheLoop.py를 찾을 수 없습니다.")
    print("이 파일은 basicChatbotHumanInTheLoop.py와 같은 디렉토리에 있어야 합니다.")
    sys.exit(1)

def get_interrupted_threads() -> list:
    """SQLite에서 interrupt 상태인 스레드들을 조회"""
    try:
        # SQLite 연결 (파일 DB 사용)
        conn = sqlite3.connect("./chatbot.db")
        cursor = conn.cursor()
        
        # checkpoints 테이블에서 interrupt 상태인 스레드 조회
        cursor.execute("""
            SELECT thread_id, config, checkpoint 
            FROM checkpoints 
            WHERE checkpoint LIKE '%interrupt%' OR checkpoint LIKE '%Command%'
        """)
        
        interrupted_threads = []
        for row in cursor.fetchall():
            thread_id, config, checkpoint = row
            try:
                checkpoint_data = json.loads(checkpoint)
                if 'next' in checkpoint_data and checkpoint_data['next'] == 'tools':
                    interrupted_threads.append({
                        'thread_id': thread_id,
                        'config': json.loads(config) if config else {},
                        'checkpoint': checkpoint_data
                    })
            except json.JSONDecodeError:
                continue
        
        conn.close()
        return interrupted_threads
        
    except Exception as e:
        print(f"❌ interrupt 스레드 조회 중 오류: {e}")
        return []

def get_thread_interrupt_info(thread_id: str) -> Optional[Dict[str, Any]]:
    """특정 스레드의 interrupt 정보 조회"""
    try:
        # 실제로는 메인 프로그램의 그래프 상태를 확인해야 함
        # 여기서는 간단한 시뮬레이션
        return {
            'thread_id': thread_id,
            'status': 'interrupted',
            'query': 'AI가 도움이 필요합니다. 답변을 입력해주세요.',
            'timestamp': datetime.now().isoformat()
        }
    except Exception as e:
        print(f"❌ 스레드 {thread_id} 정보 조회 중 오류: {e}")
        return None

def handle_human_input(thread_id: str, human_response: str) -> bool:
    """human input을 받아서 메인 프로그램에 전달"""
    try:
        print(f"🔄 스레드 '{thread_id}'에서 대화를 재개합니다...")
        
        # 메인 프로그램의 resume_from_interrupt 함수 호출
        result = resume_from_interrupt(thread_id, human_response)
        
        if result and result.get("status") == "completed":
            print("✅ 대화가 성공적으로 재개되었습니다!")
            return True
        elif result and result.get("status") == "interrupted":
            print("🔄 또 다른 human input이 필요합니다.")
            return False
        else:
            print(f"❌ 대화 재개 중 오류: {result.get('message', 'Unknown error')}")
            return False
            
    except Exception as e:
        print(f"❌ human input 처리 중 오류: {e}")
        return False

def show_available_threads():
    """사용 가능한 interrupt 스레드들을 표시"""
    print("\n📋 사용 가능한 interrupt 스레드:")
    print("-" * 50)
    
    # 실제 SQLite에서 조회하는 대신 시뮬레이션
    # 실제 구현에서는 get_interrupted_threads() 사용
    threads = [
        {'thread_id': 'default', 'status': 'interrupted', 'query': 'AI가 도움이 필요합니다.'},
        {'thread_id': 'user_123', 'status': 'interrupted', 'query': '전문가 의견이 필요합니다.'}
    ]
    
    if not threads:
        print("❌ 현재 interrupt 상태인 스레드가 없습니다.")
        return []
    
    for i, thread in enumerate(threads, 1):
        print(f"{i}. 스레드 ID: {thread['thread_id']}")
        print(f"   상태: {thread['status']}")
        print(f"   질문: {thread['query']}")
        print()
    
    return threads

def main():
    """메인 함수"""
    print("🤖 Human Input Handler")
    print("=" * 50)
    print("interrupt 상태에서 human input을 처리하는 프로그램입니다.")
    print()
    
    while True:
        print("\n📋 메뉴:")
        print("1. interrupt 스레드 목록 보기")
        print("2. 특정 스레드에 답변 입력")
        print("3. 스레드 정보 보기")
        print("4. 대화 기록 보기")
        print("5. 도움말")
        print("6. 종료")
        
        try:
            choice = input("\n선택하세요 (1-6): ").strip()
            
            if choice == "1":
                # interrupt 스레드 목록 보기
                threads = show_available_threads()
                
            elif choice == "2":
                # 특정 스레드에 답변 입력
                thread_id = input("스레드 ID를 입력하세요: ").strip()
                if not thread_id:
                    print("❌ 스레드 ID를 입력해주세요.")
                    continue
                
                # 스레드 정보 확인
                thread_info = get_thread_interrupt_info(thread_id)
                if not thread_info:
                    print(f"❌ 스레드 '{thread_id}'를 찾을 수 없거나 interrupt 상태가 아닙니다.")
                    continue
                
                print(f"\n🤖 AI 질문: {thread_info.get('query', 'Unknown')}")
                print(f"📅 시간: {thread_info.get('timestamp', 'Unknown')}")
                
                human_response = input("\n💬 답변을 입력하세요: ").strip()
                if not human_response:
                    print("❌ 답변을 입력해주세요.")
                    continue
                
                # human input 처리
                success = handle_human_input(thread_id, human_response)
                if success:
                    print("✅ 답변이 성공적으로 처리되었습니다!")
                else:
                    print("⚠️ 답변 처리 중 문제가 발생했습니다.")
                
            elif choice == "3":
                # 스레드 정보 보기
                thread_id = input("스레드 ID를 입력하세요 (기본값: default): ").strip() or "default"
                get_thread_info(thread_id)
                
            elif choice == "4":
                # 대화 기록 보기
                thread_id = input("스레드 ID를 입력하세요 (기본값: default): ").strip() or "default"
                show_conversation_history(thread_id)
                
            elif choice == "5":
                # 도움말
                print("\n📖 도움말:")
                print("1. interrupt 스레드 목록: 현재 대기 중인 human input 요청들을 확인합니다.")
                print("2. 답변 입력: 특정 스레드에 대해 AI의 질문에 답변합니다.")
                print("3. 스레드 정보: 특정 스레드의 상태와 메시지 수를 확인합니다.")
                print("4. 대화 기록: 특정 스레드의 전체 대화 기록을 확인합니다.")
                print("5. 이 프로그램은 메인 챗봇 프로그램과 함께 작동합니다.")
                print("6. 메인 프로그램에서 interrupt가 발생하면 이 프로그램을 사용하세요.")
                
            elif choice == "6":
                print("👋 Human Input Handler를 종료합니다.")
                break
                
            else:
                print("❌ 1-6 사이의 숫자를 입력해주세요.")
                
        except KeyboardInterrupt:
            print("\n👋 프로그램이 중단되었습니다.")
            break
        except Exception as e:
            print(f"❌ 예상치 못한 오류가 발생했습니다: {e}")

if __name__ == "__main__":
    main() 