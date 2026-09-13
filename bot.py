import asyncio
import logging
import os
from datetime import datetime, timezone, timedelta
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ChatPermissions
from aiogram.enums import ChatMemberStatus, ContentType

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "0"))
CHANNEL_LINK = os.getenv("CHANNEL_LINK", "")
WARNING_DELETE_DELAY = 60
GROUP_CHAT_ID = int(os.getenv("GROUP_CHAT_ID", "0"))

# Часовой пояс Москва UTC+3
MSK = timezone(timedelta(hours=3))

# Расписание: чат закрыт с 23:00 до 09:00
CLOSE_HOUR = 23
OPEN_HOUR = 9

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Флаг текущего состояния чата
chat_is_closed = False
# ID сообщения "Спокойной ночи" для удаления
goodnight_message_id = None


def is_night_time() -> bool:
    """Проверяет, попадает ли текущее время в закрытый период (23:00 - 09:00 МСК)"""
    now = datetime.now(MSK)
    return now.hour >= CLOSE_HOUR or now.hour < OPEN_HOUR


async def close_chat():
    """Закрывает чат и отправляет сообщение"""
    global chat_is_closed, goodnight_message_id
    try:
        await bot.set_chat_permissions(
            chat_id=GROUP_CHAT_ID,
            permissions=ChatPermissions(
                can_send_messages=False,
                can_send_audios=False,
                can_send_documents=False,
                can_send_photos=False,
                can_send_videos=False,
                can_send_video_notes=False,
                can_send_voice_notes=False,
                can_send_polls=False,
                can_send_other_messages=False,
                can_add_web_page_previews=False,
            ),
        )
        chat_is_closed = True
        logger.info("Чат закрыт")

        msg = await bot.send_message(
            chat_id=GROUP_CHAT_ID,
            text="🌙 Уважаемые участники, чат закрыт до 09:00. Спокойной ночи!",
        )
        goodnight_message_id = msg.message_id
        logger.info(f"Отправлено сообщение 'Спокойной ночи', id={msg.message_id}")
    except Exception as e:
        logger.error(f"Ошибка закрытия чата: {e}")


async def open_chat():
    """Открывает чат и удаляет ночное сообщение"""
    global chat_is_closed, goodnight_message_id
    try:
        await bot.set_chat_permissions(
            chat_id=GROUP_CHAT_ID,
            permissions=ChatPermissions(
                can_send_messages=True,
                can_send_audios=True,
                can_send_documents=True,
                can_send_photos=True,
                can_send_videos=True,
                can_send_video_notes=True,
                can_send_voice_notes=True,
                can_send_polls=True,
                can_send_other_messages=True,
                can_add_web_page_previews=True,
            ),
        )
        chat_is_closed = False
        logger.info("Чат открыт")

        if goodnight_message_id:
            try:
                await bot.delete_message(
                    chat_id=GROUP_CHAT_ID,
                    message_id=goodnight_message_id,
                )
                logger.info("Сообщение 'Спокойной ночи' удалено")
            except Exception:
                pass
            goodnight_message_id = None
    except Exception as e:
        logger.error(f"Ошибка открытия чата: {e}")


async def schedule_loop():
    """Каждые 30 секунд проверяет время и открывает/закрывает чат"""
    global chat_is_closed
    while True:
        try:
            night = is_night_time()
            if night and not chat_is_closed:
                await close_chat()
            elif not night and chat_is_closed:
                await open_chat()
        except Exception as e:
            logger.error(f"Ошибка в schedule_loop: {e}")
        await asyncio.sleep(30)


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


# --- Фоновая задача: каждые 5 секунд откреляем ---
async def unpin_loop():
    while True:
        try:
            chat = await bot.get_chat(GROUP_CHAT_ID)
            if chat.pinned_message:
                pinned = chat.pinned_message
                is_from_channel = (
                    pinned.sender_chat and pinned.sender_chat.id == CHANNEL_ID
                ) or pinned.is_automatic_forward

                if is_from_channel:
                    await bot.unpin_chat_message(
                        chat_id=GROUP_CHAT_ID,
                        message_id=pinned.message_id,
                    )
                    logger.info(f"Откреплено сообщение {pinned.message_id} из канала")
        except Exception as e:
            logger.error(f"Ошибка в unpin_loop: {e}")
        await asyncio.sleep(5)


@dp.message(F.chat.type.in_({"group", "supergroup"}))
async def handle_all_group_messages(message: types.Message):
    # 1) Системное сообщение о закреплении
    if message.content_type == ContentType.PINNED_MESSAGE:
        logger.info(f"Обнаружено закрепление: {message.pinned_message.message_id}")
        try:
            await bot.unpin_chat_message(
                chat_id=message.chat.id,
                message_id=message.pinned_message.message_id,
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
                    [
                        InlineKeyboardButton(
                            text="📢 Подписаться на канал",
                            url=CHANNEL_LINK,
                        )
                    ]
                ],
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
    asyncio.create_task(unpin_loop())
    logger.info("Фоновая задача unpin_loop запущена")
    asyncio.create_task(schedule_loop())
    logger.info("Фоновая задача schedule_loop запущена")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
