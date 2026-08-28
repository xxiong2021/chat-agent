from app.agent.agent import ask_agent
from app.agent.memory import ConversationMemory


memory = ConversationMemory()


def main():

    print("================================")
    print("      Personal AI Agent")
    print("================================")
    print("输入 exit 退出")
    print("输入 clear 清除当前对话\n")

    user_id = "local_user"

    while True:

        message = input("你 > ")

        if message.lower() == "exit":
            break

        if message.lower() == "clear":

            memory.clear(user_id)

            print(
                "\n对话记忆已经清除。\n"
            )

            continue

        try:

            # 获取历史对话
            history = memory.get_history(
                user_id
            )

            # 调用 Agent
            answer = ask_agent(
                message,
                history,
            )

            # 保存用户消息
            memory.add_message(
                user_id,
                "user",
                message,
            )

            # 保存 Agent 回复
            memory.add_message(
                user_id,
                "assistant",
                answer,
            )

            print(
                f"\nAgent > {answer}\n"
            )

        except Exception as e:

            print(
                f"\n错误：{e}\n"
            )


if __name__ == "__main__":
    main()
