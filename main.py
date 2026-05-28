"""
XF 模具智能体平台 - CLI 交互入口
"""
from langchain_core.messages import HumanMessage, AIMessage
from state import AgentState
from graph import build_graph


def print_banner():
    print("\n" + "=" * 58)
    print("  XF 模具智能体平台  |  研发 + 质量双智能体  ")
    print("=" * 58)
    print("  输入 'quit' / 'exit' 退出")
    print("  输入 'clear' 清空记忆")
    print("=" * 58)


def truncate_history(history: list, max_rounds: int = 5) -> list:
    """截断到最近 N 轮"""
    if len(history) > max_rounds * 2:
        return history[-(max_rounds * 2):]
    return history


if __name__ == "__main__":
    print_banner()
    app = build_graph()
    chat_history: list = []

    while True:
        try:
            user_input = input("\nUser > ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n\n再见！")
            break

        if not user_input:
            continue
        if user_input.lower() in ["quit", "exit", "q"]:
            print("\n再见！")
            break
        if user_input.lower() == "clear":
            chat_history.clear()
            print("[记忆已清空]\n")
            continue

        chat_history.append(HumanMessage(content=user_input, name="user"))
        truncated = truncate_history(chat_history)

        state: AgentState = {
            "messages": truncated,
            "sender": "user",
            "next_agent": "",
            "intent": "",
            "rag_result": "",
            "rag_is_relevant": False,
            "task_completed": False,
        }

        try:
            final_state = app.invoke(state, config={"recursion_limit": 12})
        except Exception as e:
            print(f"\n[执行出错] {e}")
            chat_history.pop()
            continue

        messages = final_state.get("messages", [])
        if messages:
            answer = messages[-1].content
            preview = answer[:2000] + "..." if len(answer) > 2000 else answer
            print("-" * 58)
            print(f"Agent > {preview}")
            print("-" * 58)
            chat_history.append(AIMessage(content=answer, name="agent"))
        else:
            print("\n[警告] Agent 未返回有效回答")

        print()
