#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Basic test to verify the agent structure is correct
"""
import sys
import io
from pathlib import Path

# Fix terminal encoding on Windows
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Add current dir to path
sys.path.insert(0, str(Path(__file__).parent))

def test_imports():
    """Test that all modules can be imported"""
    print("Testing imports...")

    try:
        import config
        print("✓ config")

        import message_processor
        print("✓ message_processor")

        import state_manager
        print("✓ state_manager")

        import task_linker
        print("✓ task_linker")

        print("\n✓ All imports successful!")
        return True

    except ImportError as e:
        print(f"\n✗ Import error: {e}")
        return False

def test_message_processor():
    """Test message processor"""
    print("\nTesting MessageProcessor...")

    from message_processor import MessageProcessor

    # Mock WhatsApp message
    wa_msg = {
        'id': 'test_1',
        'from': '972501234567',
        'timestamp': '2024-01-15T10:30:00',
        'type': 'text',
        'text': 'TODO: צריך לסיים את הפרויקט עד יום שישי',
        'sender': 'אלי'
    }

    processed = MessageProcessor.process_whatsapp_message(wa_msg)

    assert processed['platform'] == 'whatsapp'
    assert processed['has_task'] == True
    assert 'TODO' in processed['task_keywords']
    print("✓ WhatsApp message processing works")

    # Mock Gmail message
    gmail_msg = {
        'id': 'gmail_1',
        'from': 'client@example.com',
        'to': 'me@example.com',
        'subject': 'דחוף: בקשה לעדכון מדיום',
        'date': '2024-01-15T10:30:00',
        'body': 'אנא עדכן את המדיום בהקדם האפשרי',
        'timestamp': '2024-01-15T10:30:00'
    }

    processed = MessageProcessor.process_gmail_message(gmail_msg)

    assert processed['platform'] == 'gmail'
    assert processed['urgency'] == 'urgent'
    print("✓ Gmail message processing works")

    # Test task extraction
    task = MessageProcessor.extract_task_from_message(processed)
    assert task['status'] == 'open'
    assert task['priority'] == 'urgent'
    print("✓ Task extraction works")

    return True

def test_config():
    """Test config loading"""
    print("\nTesting configuration...")

    from config import BASE_DIR, CLAUDE_MODEL, TASK_KEYWORDS

    assert BASE_DIR.exists()
    print("✓ Base directory exists")

    assert CLAUDE_MODEL in ['claude-opus-4-6', 'claude-sonnet-4-6', 'claude-haiku-4-5-20251001']
    print(f"✓ Claude model configured: {CLAUDE_MODEL}")

    assert len(TASK_KEYWORDS) > 0
    print(f"✓ {len(TASK_KEYWORDS)} task keywords configured")

    return True

def test_database():
    """Test database creation"""
    print("\nTesting database...")

    from state_manager import StateManager, Base, engine
    import uuid

    # Create tables
    Base.metadata.drop_all(engine)  # Clean slate
    Base.metadata.create_all(engine)
    print("✓ Database tables created")

    # Test StateManager
    sm = StateManager()

    # Add mock message
    from datetime import datetime
    test_msg_id = f"test_msg_{uuid.uuid4().hex[:8]}"
    msg_id = sm.add_message({
        'id': test_msg_id,
        'platform': 'whatsapp',
        'sender': 'Test User',
        'sender_id': 'test_123',
        'content': 'Test message',
        'timestamp': datetime.now(),
        'metadata': {}
    })

    assert msg_id == test_msg_id
    print("✓ Message stored in database")

    # Add mock task
    test_task_id = f"test_task_{uuid.uuid4().hex[:8]}"
    task_id = sm.add_task({
        'id': test_task_id,
        'title': 'Test Task',
        'description': 'This is a test task',
        'source_message_id': msg_id,
        'platform': 'whatsapp',
        'status': 'open',
        'priority': 'normal',
        'metadata': {}
    })

    assert task_id == test_task_id
    print("✓ Task stored in database")

    # Get analytics (use larger time window since we just added data)
    analytics = sm.get_analytics(hours=24)
    assert analytics['total_messages'] >= 1
    assert analytics['total_tasks'] >= 1
    print("✓ Analytics query works")

    sm.close()
    return True

def main():
    """Run all tests"""
    print("="*50)
    print("WhatsApp + Gmail Agent - Basic Tests")
    print("="*50 + "\n")

    tests = [
        ("Imports", test_imports),
        ("Config", test_config),
        ("Message Processor", test_message_processor),
        ("Database", test_database)
    ]

    results = []
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            print(f"\n✗ {name} failed: {e}")
            import traceback
            traceback.print_exc()
            results.append((name, False))

    print("\n" + "="*50)
    print("Test Results:")
    print("="*50)

    all_passed = True
    for name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status}: {name}")
        if not result:
            all_passed = False

    print("\n" + "="*50)
    if all_passed:
        print("✓ All tests passed!")
        print("\nNext steps:")
        print("1. Edit .env with your API credentials")
        print("2. Run: python main.py")
        print("3. Open: http://localhost:5000")
        return 0
    else:
        print("✗ Some tests failed. Check the output above.")
        return 1

if __name__ == '__main__':
    sys.exit(main())
