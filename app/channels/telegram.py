import os

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    Application,
    ContextTypes,
    MessageHandler,
    filters,
)

from app.agent.agent import ask_agent
from app.agent.memory import ConversationMemory
from app.agent.users import UserManager


load_dotenv()


telegram_token = os.getenv("TELEGRAM_BOT_TOKEN")

if not telegram_token:
    raise RuntimeError(
        "没有找到 TELEGRAM_BOT_TOKEN，请检查 .env 文件"
    )


# 用户管理器
user_manager = UserManager()

# 对话记忆
memory = ConversationMemory()


async def reply_agent(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    """
    接收 Telegram 消息，
    验证用户身份，
    然后交给 Agent 处理。
    """
    if not update.message or not update.message.text:
        return

    if not update.effective_user:
        return

    print(
        f"[Telegram] User ID: {update.effective_user.id}"
    )

    # Telegram 用户唯一 ID
    telegram_id = update.effective_user.id

    # 获取用户信息
    user = user_manager.get_user(telegram_id)

    # ------------------------------------------------
    # 身份验证
    # ------------------------------------------------

    if not user_manager.is_allowed(telegram_id):

        print(
            f"[Auth] 拒绝访问："
            f"Telegram ID = {telegram_id}"
        )

        await update.message.reply_text(
            "你还没有获得使用这个 Agent 的权限。"
        )

        return

    # ------------------------------------------------
    # 用户信息
    # ------------------------------------------------

    user_name = user_manager.get_name(
        telegram_id
    )

    user_role = user_manager.get_role(
        telegram_id
    )

    print(
        f"[Auth] 用户通过："
        f"{user_name} "
        f"(Telegram ID={telegram_id}, "
        f"role={user_role})"
    )

    # ------------------------------------------------
    # 获取用户消息
    # ------------------------------------------------

    user_text = update.message.text

    print(
        f"[Telegram] "
        f"{user_name}: {user_text}"
    )

    # ------------------------------------------------
    # 用户独立的对话记忆
    # ------------------------------------------------

    user_id = (
        f"telegram:{telegram_id}"
    )
    print(
        f"[Telegram DEBUG] "
        f"repr(user_text)={user_text!r}, "
        f"user_id={user_id}"
    )
    history = memory.get_history(
        user_id
    )

    # ------------------------------------------------
    # 调用 Agent
    # ------------------------------------------------

    try:

        ai_reply = ask_agent(
            user_text,
            history,
            user_id,
        )

    except Exception as e:

        print(
            f"[Agent] 执行失败：{e}"
        )

        await update.message.reply_text(
            "Agent 执行过程中发生错误，请检查服务器日志。"
        )

        return

    # ------------------------------------------------
    # 保存用户消息
    # ------------------------------------------------

    memory.add_message(
        user_id,
        "user",
        user_text,
    )

    # ------------------------------------------------
    # 保存 Agent 回复
    # ------------------------------------------------

    memory.add_message(
        user_id,
        "assistant",
        ai_reply,
    )

    # ------------------------------------------------
    # 返回 Telegram
    # ------------------------------------------------

    await update.message.reply_text(
        ai_reply
    )


def main():

    app = (
        Application.builder()
        .token(telegram_token)
        .build()
    )

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            reply_agent,
        )
    )

    print(
        "Telegram Agent started."
    )

    app.run_polling()


if __name__ == "__main__":
    main()
