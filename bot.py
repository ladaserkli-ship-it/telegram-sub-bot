import asyncio
import logging
import os
from aiogram import Bot, Dispatcher, types, F
from aiogram.enums import ChatMemberStatus
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# ===================== НАСТРОЙКИ =====================
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")
CHANNEL_LINK = os.getenv("CHANNEL_LINK")
WARNING_DELETE_DELAY = 60
# =====================================================

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


async def is_subscribed(user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        return member.status in [
            ChatMemberStatus.MEMBER,
            ChatMemberStatus.ADMINISTRATOR,
            ChatMemberStatus.CREATOR,
        ]
    except Exception as e:
        logger.error(f"Ошибка проверки подписки для {user_id}: {e}")
        return True


async def delete_after_delay(chat_id: int, message_id: int, delay: int):
    await asyncio.sleep(delay)
    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
    except Exception as e:
        logger.error(f"Не удалось удалить предупреждение: {e}")


@dp.message(F.chat.type.in_({"group", "supergroup"}))
async def check_subscription(message: types.Message):
    # Пропускаем сообщения от ботов
    if message.from_user is None or message.from_user.is_bot:
        return

    # Пропускаем автоматические пересылки из канала в чат
    if message.is_automatic_forward:
        return

    # Если сообщение от имени канала/чата
    if message.sender_chat is not None:
        # Пропускаем только СВОЙ канал
        if str(message.sender_chat.id) == str(CHANNEL_ID):
            return
        # Все остальные каналы и чаты — удаляем
        try:
            await message.delete()
        except Exception as e:
            logger.error(f"Не удалось удалить сообщение от канала: {e}")
        return

    user_id = message.from_user.id
    subscribed = await is_subscribed(user_id)

    if subscribed:
        return

    try:
        await message.delete()
    except Exception as e:
        logger.error(f"Не удалось удалить сообщение: {e}")

    user_name = message.from_user.first_name or "Друг"
    warning_text = (
        f"👋 {user_name}, чтобы писать в этом чате, "
        f"нужно подписаться на наш канал!\n\n"
        f"Подпишись по кнопке ниже — и возвращайся 😊"
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📢 Подписаться на канал", url=CHANNEL_LINK)]
        ]
    )

    try:
        warning_msg = await message.answer(warning_text, reply_markup=keyboard)
        asyncio.create_task(
            delete_after_delay(warning_msg.chat.id, warning_msg.message_id, WARNING_DELETE_DELAY)
        )
    except Exception as e:
        logger.error(f"Не удалось отправить предупреждение: {e}")


async def main():
    logger.info("Бот запущен!")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
