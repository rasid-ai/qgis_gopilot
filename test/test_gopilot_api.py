"""
Quick test script to verify GoPilot API responses
Run this in QGIS Python Console to debug API issues
"""

# NOTE, to run open QGIS then open Python Console 
# import sys
# sys.path.insert(0, r'path of the plugin on your computer')
# from test.test_gopilot_api import test_gopilot_api
# test_gopilot_api()

def test_gopilot_api():
    """Test GoPilot API and print response structure"""
    from rasid_components.rasid_client import RasidClient

    print("="*60)
    print("Testing GoPilot API")
    print("="*60)

    # Initialize client
    client = RasidClient()

    # Load API key
    if not client.load_api_key():
        print("❌ No API key found. Please login first.")
        return

    print(f"✅ API key loaded")
    print(f"✅ GoPilot client initialized: {client.gopilot is not None}")

    if not client.gopilot:
        print("❌ GoPilot client is None")
        return

    try:
        # Test 1: Create session
        print("\n" + "-"*60)
        print("TEST 1: Create Session")
        print("-"*60)
        session = client.gopilot.create_session(title="Test Chat")
        print(f"✅ Session created")
        print(f"   Type: {type(session)}")
        print(f"   Data: {session}")

        if not isinstance(session, dict):
            print(f"❌ ERROR: Session should be dict, got {type(session)}")
            return

        session_id = session.get('id')
        print(f"   Session ID: {session_id}")

        # Test 2: Send message
        print("\n" + "-"*60)
        print("TEST 2: Send Message")
        print("-"*60)
        result = client.gopilot.send_message(
            session_id=session_id,
            content="Hello, this is a test message"
        )
        print(f"✅ Message sent")
        print(f"   Type: {type(result)}")
        print(f"   Keys: {result.keys() if isinstance(result, dict) else 'N/A'}")
        print(f"   Full response: {result}")

        if not isinstance(result, dict):
            print(f"❌ ERROR: Result should be dict, got {type(result)}")
            print(f"   Content: {result}")
            return

        # Check expected keys
        print("\n   Checking response structure:")
        if 'user_message' in result:
            print(f"   ✅ user_message: {type(result['user_message'])}")
        else:
            print(f"   ⚠️  user_message: missing")

        if 'task' in result:
            print(f"   ✅ task: {type(result['task'])}")
        else:
            print(f"   ⚠️  task: missing")

        if 'message' in result:
            print(f"   ✅ message: {type(result['message'])}")
            if isinstance(result['message'], dict):
                content = result['message'].get('content', '')
                print(f"      Content: {content[:100]}...")
            else:
                print(f"      Value: {result['message']}")
        else:
            print(f"   ⚠️  message: missing")

        # Test 3: Get messages
        print("\n" + "-"*60)
        print("TEST 3: Get Messages")
        print("-"*60)
        messages = client.gopilot.get_messages(session_id)
        print(f"✅ Messages retrieved")
        print(f"   Type: {type(messages)}")
        print(f"   Count: {len(messages) if isinstance(messages, list) else 'N/A'}")
        if isinstance(messages, list) and len(messages) > 0:
            print(f"   First message: {messages[0]}")

        # Test 4: Get session history
        print("\n" + "-"*60)
        print("TEST 4: Get Session History")
        print("-"*60)
        history = client.gopilot.get_session_history()
        print(f"✅ History retrieved")
        print(f"   Type: {type(history)}")
        if isinstance(history, dict):
            print(f"   Keys: {history.keys()}")
            print(f"   Count: {history.get('count', 'N/A')}")
            results = history.get('results', [])
            print(f"   Sessions: {len(results)}")

        print("\n" + "="*60)
        print("✅ ALL TESTS PASSED")
        print("="*60)

    except Exception as e:
        import traceback
        print("\n" + "="*60)
        print("❌ ERROR OCCURRED")
        print("="*60)
        print(f"Error: {e}")
        print("\nFull traceback:")
        print(traceback.format_exc())

if __name__ == "__main__":
    test_gopilot_api()