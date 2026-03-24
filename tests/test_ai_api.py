"""AI API connectivity tests — P0.5

Run: conda activate moldgen && python tests/test_ai_api.py

Requires .env with API keys.
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def main():
    print("=" * 50)
    print("MoldGen AI API Connectivity Test")
    print("=" * 50)

    from moldgen.ai.service_manager import AIServiceManager

    mgr = AIServiceManager()
    status = mgr.get_status()

    print("\nConfigured services:")
    print(f"  DeepSeek: {'YES' if status.deepseek else 'NO'}")
    print(f"  Qwen:     {'YES' if status.qwen else 'NO'}")
    print(f"  Kimi:     {'YES' if status.kimi else 'NO'}")
    print(f"  Wanxiang: {'YES' if status.wanxiang else 'NO'}")
    print(f"  Tripo3D:  {'YES' if status.tripo3d else 'NO'}")

    results = []

    for svc, configured in [
        ("deepseek", status.deepseek),
        ("qwen", status.qwen),
        ("kimi", status.kimi),
    ]:
        if configured:
            print(f"\n--- Testing {svc} ---")
            result = await mgr.test_connection(svc)
            print(f"  Result: {'PASS' if result['success'] else 'FAIL'}")
            if result.get("response"):
                print(f"  Response: {result['response']}")
            if result.get("error"):
                print(f"  Error: {result['error']}")
            if result.get("usage"):
                print(f"  Tokens: {result['usage']}")
            results.append(result["success"])
        else:
            print(f"\n[SKIP] {svc} — no API key")

    if not results:
        print("\n" + "-" * 50)
        print("No AI API keys configured.")
        print("Create .env file from .env.example and add your keys.")
        print("AI API infrastructure is ready — awaiting keys.")

    print("\n" + "=" * 50)
    passed = sum(results)
    total = len(results)
    if total > 0:
        print(f"Results: {passed}/{total} services connected")
    else:
        print("Infrastructure verified — no keys to test")
    print("=" * 50)


if __name__ == "__main__":
    asyncio.run(main())
