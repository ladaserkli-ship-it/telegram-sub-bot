import asyncio
import logging
import os
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.enums import ChatMemberStatus, ContentType

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "0"))
CHANNEL_LINK = os.getenv("CHANNEL_LINK", "")
WARNING_DELETE_DELAY = 60
# ID группового чата (тот же формат, что CHANNEL_ID, но для чата)
GROUP_CHAT_ID = int(os.getenv("GROUP_CHAT_ID", "0"))

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
        logger.error(f"Ошибка проверки подписки: {e}")
        return True


async def delete_after_delay(message: types.Message, delay: int):
    await asyncio.sleep(delay)
    try:
        await message.delete()
    except Exception:
        pass


# --- Фоновая задача: каждые 5 секунд проверяем и откреляем ---
async def unpin_loop():
    while True:
        try:
            chat = await bot.get_chat(GROUP_CHAT_ID)
            if chat.pinned_message:
                # Если закреплённое сообщение пришло из канала — откреляем
                pinned = chat.pinned_message
                is_from_channel = (
                    pinned.sender_chat and pinned.sender_chat.id == CHANNEL_ID
                ) or pinned.is_automatic_forward
                
                if is_from_channel:
                    await bot.unpin_chat_message(
                        chat_id=GROUP_CHAT_ID,
                        message_id=pinned.message_id
                    )
                    logger.info(f"Откреплено сообщение {pinned.message_id} из канала")
        except Exception as e:
            logger.error(f"Ошибка в unpin_loop: {e}")
        await asyncio.sleep(5)


# --- Обработчик системных уведомлений о закреплении ---
@dp.message(F.chat.type.in_({"group", "supergroup"}))
async def handle_all_group_messages(message: types.Message):
    # 1) Системное сообщение о закреплении — удаляем уведомление
    if message.content_type == ContentType.PINNED_MESSAGE:
        logger.info(f"Обнаружено закрепление: {message.pinned_message.message_id}")
        try:
            await bot.unpin_chat_message(
                chat_id=message.chat.id,
                message_id=message.pinned_message.message_id
            )
            logger.info("Откреплено через обработчик")
        except Exception as e:
            logger.error(f"Не удалось открепить: {e}")
        try:
            await message.delete()
        except Exception:
            pass
        return

    # 2) Пропускаем ботов
    if message.from_user and message.from_user.is_bot:
        return

    # 3) Пропускаем автопересылки из канала
    if message.is_automatic_forward:
        return

    # 4) Пропускаем сообщения от самого канала
    if message.sender_chat and message.sender_chat.id == CHANNEL_ID:
        return

    # 5) Проверка подписки
    if message.from_user:
        subscribed = await is_subscribed(message.from_user.id)
        if not subscribed:
            try:
                await message.delete()
                logger.info(f"Удалено сообщение от {message.from_user.id} (не подписан)")
            except Exception as e:
                logger.error(f"Не удалось удалить сообщение: {e}")

            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(
                        text="📢 Подписаться на канал",
                        url=CHANNEL_LINK
                    )]
                ]
            )
            try:
                warning = await message.answer(
                    f"👋 {message.from_user.first_name}, чтобы писать в чате, "
                    f"подпишитесь на канал!",
                    reply_markup=keyboard,
                )
                asyncio.create_task(delete_after_delay(warning, WARNING_DELETE_DELAY))
            except Exception as e:
                logger.error(f"Не удалось отправить предупреждение: {e}")


async def main():
    logger.info("Бот запущен!")
    await bot.delete_webhook(drop_pending_updates=True)
    # Запускаем фоновую проверку откреления
    asyncio.create_task(unpin_loop())
    logger.info("Фоновая задача unpin_loop запущена")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
