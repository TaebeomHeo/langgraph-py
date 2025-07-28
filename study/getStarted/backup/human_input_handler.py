#!/usr/bin/env python3
"""
Human Input Handler for Human-in-the-Loop Chatbot
인간 전문가가 pending interrupt를 확인하고 응답을 제공하는 프로그램
"""

import os
import sys
import sqlite3
from datetime import datetime
from typing import List, Dict, Optional

def get_pending_interrupts() -> List[Dict]:
    """pending 상태인 interrupt들을 조회"""
    try:
        conn = sqlite3.connect('interrupt_state.db')
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT id, thread_id, query, tool_name, timestamp, status
            FROM interrupt_state 
            WHERE status = 'pending'
            ORDER BY timestamp ASC
        """)
        
        interrupts = []
        for row in cursor.fetchall():
            interrupts.append({
                'id': row[0],
                'thread_id': row[1],
                'query': row[2],
                'tool_name': row[3],
                'timestamp': row[4],
                'status': row[5]
            })
        
        conn.close()
        return interrupts
        
    except sqlite3.Error as e:
        print(f"❌ 데이터베이스 오류: {e}")
        return []

def update_interrupt_status(interrupt_id: int, status: str, human_response: str = None) -> bool:
    """interrupt 상태를 업데이트"""
    try:
        conn = sqlite3.connect('interrupt_state.db')
        cursor = conn.cursor()
        
        if human_response:
            cursor.execute("""
                UPDATE interrupt_state 
                SET status = ?, human_response = ?, timestamp = ?
                WHERE id = ?
            """, (status, human_response, datetime.now().isoformat(), interrupt_id))
        else:
            cursor.execute("""
                UPDATE interrupt_state 
                SET status = ?, timestamp = ?
                WHERE id = ?
            """, (status, datetime.now().isoformat(), interrupt_id))
        
        conn.commit()
        conn.close()
        return True
        
    except sqlite3.Error as e:
        print(f"❌ 데이터베이스 오류: {e}")
        return False

def show_pending_interrupts():
    """대기 중인 interrupt들을 표시"""
    interrupts = get_pending_interrupts()
    
    if not interrupts:
        print("📝 현재 대기 중인 interrupt가 없습니다.")
        return
    
    print(f"\n📋 대기 중인 interrupt들 ({len(interrupts)}개):")
    print("=" * 60)
    
    for i, interrupt in enumerate(interrupts, 1):
        print(f"\n{i}. ID: {interrupt['id']}")
        print(f"   Thread: {interrupt['thread_id']}")
        print(f"   Query: {interrupt['query']}")
        print(f"   Tool: {interrupt['tool_name']}")
        print(f"   Time: {interrupt['timestamp']}")
        print(f"   Status: {interrupt['status']}")

def handle_interrupt_response(interrupt_id: int, human_response: str) -> bool:
    """인간 응답을 처리하고 Command 상태를 저장"""
    try:
        # interrupt 상태를 completed로 업데이트
        if update_interrupt_status(interrupt_id, 'completed', human_response):
            # Command 상태를 저장하여 메인 프로세스가 이를 처리할 수 있도록 함
            conn = sqlite3.connect('interrupt_state.db')
            cursor = conn.cursor()
            
            # command_queue 테이블 생성 (없으면)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS command_queue (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    thread_id TEXT,
                    command_type TEXT,
                    command_data TEXT,
                    timestamp TEXT,
                    status TEXT DEFAULT 'pending'
                )
            ''')
            
            # 인간 응답을 Command로 저장
            cursor.execute('''
                INSERT INTO command_queue (thread_id, command_type, command_data, timestamp)
                SELECT thread_id, 'human_response', ?, ?
                FROM interrupt_state WHERE id = ?
            ''', (human_response, datetime.now().isoformat(), interrupt_id))
            
            conn.commit()
            conn.close()
            
            print(f"✅ Interrupt {interrupt_id}에 대한 응답이 저장되었습니다.")
            print("📋 메인 프로세스를 다시 시작하여 Command를 처리하세요.")
            return True
        else:
            return False
            
    except Exception as e:
        print(f"❌ 오류 발생: {e}")
        return False

def main():
    """메인 함수"""
    print("🤖 Human Input Handler for Human-in-the-Loop Chatbot")
    print("=" * 60)
    
    while True:
        try:
            print("\n📋 메뉴:")
            print("1. 대기 중인 interrupt 보기")
            print("2. interrupt에 응답하기")
            print("3. 종료")
            
            choice = input("\n선택하세요 (1-3): ").strip()
            
            if choice == '1':
                show_pending_interrupts()
                
            elif choice == '2':
                interrupts = get_pending_interrupts()
                if not interrupts:
                    print("📝 현재 대기 중인 interrupt가 없습니다.")
                    continue
                
                print("\n사용 가능한 interrupt:")
                for i, interrupt in enumerate(interrupts, 1):
                    print(f"{i}. ID {interrupt['id']}: {interrupt['query']}")
                
                try:
                    interrupt_idx = int(input("\ninterrupt 번호를 선택하세요: ")) - 1
                    if 0 <= interrupt_idx < len(interrupts):
                        selected_interrupt = interrupts[interrupt_idx]
                        
                        print(f"\n📋 Interrupt 세부 정보:")
                        print(f"Query: {selected_interrupt['query']}")
                        print(f"Thread: {selected_interrupt['thread_id']}")
                        print(f"Time: {selected_interrupt['timestamp']}")
                        
                        human_response = input("\n👤 전문가 응답을 입력하세요: ").strip()
                        if human_response:
                            success = handle_interrupt_response(selected_interrupt['id'], human_response)
                            if not success:
                                print("❌ 응답 처리에 실패했습니다.")
                        else:
                            print("❌ 빈 응답은 허용되지 않습니다.")
                    else:
                        print("❌ 잘못된 interrupt 번호입니다.")
                except ValueError:
                    print("❌ 올바른 숫자를 입력해주세요.")
                    
            elif choice == '3':
                print("👋 Human Input Handler를 종료합니다.")
                break
                
            else:
                print("❌ 올바른 선택지를 입력해주세요 (1-3).")
                
        except KeyboardInterrupt:
            print("\n\n👋 사용자에 의해 중단되었습니다.")
            break
        except Exception as e:
            print(f"❌ 예상치 못한 오류가 발생했습니다: {e}")

if __name__ == "__main__":
    main()