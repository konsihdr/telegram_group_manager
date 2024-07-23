import html
import json
import logging
import os
import traceback
from datetime import datetime

from sqlalchemy import and_
from sqlalchemy.orm import Session

from sql import Base, Groups, engine
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, ChatMember
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, filters, CallbackContext, MessageHandler, \
    CallbackQueryHandler, AIORateLimiter
from telegram.constants import ParseMode

logging.basicConfig(format='%(asctime)s %(levelname)-8s %(message)s', level=logging.INFO, datefmt='%Y-%m-%d %H:%M:%S')
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

if os.environ['BOT_TOKEN'] == "":
    logging.info('Not Bot Token Provided')
    exit()

if os.environ['ADMIN_GROUP'] == "":
    admin_group = None
else:
    admin_group = int(os.environ['ADMIN_GROUP'])


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await context.bot.send_message(chat_id=update.effective_chat.id,
                                   text="Hi, ich bin der DACH  List Bot. Ich bin dafür da, um die DACH Gruppen zu "
                                        "verwalten. Wenn du mich in deiner Gruppe hinzufügst, werde ich dir einen "
                                        "Link senden, mit dem du deine Gruppe auf die DACH Liste setzen kannst. Wenn "
                                        "du Fragen hast, wende dich bitte an die Admins der DACH Gruppe.")


async def bot_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await context.bot.send_message(chat_id=update.effective_chat.id, text=f"{os.environ['BOT_NAME']} Online")


app = ApplicationBuilder().token(os.environ['BOT_TOKEN']).rate_limiter(AIORateLimiter()).build()


async def get_chat_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await context.bot.send_message(chat_id=update.effective_chat.id, text=f'<pre>{update.effective_chat.id}</pre>',
                                   parse_mode=ParseMode.HTML)


async def me_invited_or_joined(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    new_members = update.message.new_chat_members

    if context.bot.id in [member.id for member in new_members]:
        # Bot was added to a group
        logging.info(f'bot added to group {update.effective_chat.title} ({update.effective_chat.id})')
        now = datetime.now()

        with Session(engine) as s:
            group = s.query(Groups).filter_by(group_id=update.effective_chat.id).first()
            if group:
                if group.group_deleted:
                    await update.message.reply_text(f"Oh Oh, deine Gruppe ist schon bekannt und es gibt ein Problem. "
                                                    f"Bitte wende dich an die Admins der DACH Gruppe. Deine ID ist "
                                                    f"die {update.effective_chat.id}")
                    await context.bot.leave_chat(update.effective_chat.id)
                    return
                if not group.group_deleted:
                    return
            else:
                new_group = Groups(group_name=update.effective_chat.title, group_id=update.effective_chat.id,
                                   group_joined=now, group_active=False, group_deleted=False, group_invite_link="")
                s.add(new_group)
                s.commit()
                await context.bot.send_message(
                    admin_group,
                    f"Neue Gruppe Meldet sich an: {update.effective_chat.title} ({update.effective_chat.id}) - 'https://t.me/{update.username}'",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("Zulassen", callback_data=f'accept+{update.effective_chat.id}'),
                        InlineKeyboardButton("Ablehnen", callback_data=f'decline+{update.effective_chat.id}')
                    ]])
                )
        return


async def bot_to_group_check(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    logging.info(f'got new callback {query.data}')
    logging.debug(query)

    if query.data == "ok":
        await context.bot.answer_callback_query(query.id, text="Keine Aktion durchgeführt")
        return

    group_query = int(query.data.split('+')[1])
    answer = str(query.data.split('+')[0])

    if answer == "accept":
        with Session(engine) as s:
            results = s.query(Groups).filter_by(group_id=group_query).all()
            if results:
                results[0].group_active = True
                s.commit()
        reply_markup = InlineKeyboardMarkup(
            [[InlineKeyboardButton("Angenommen - ablehnen?", callback_data=f"decline+{group_query}")]])

        json_keyboard = reply_markup.to_json()

        await context.bot.edit_message_reply_markup(
            chat_id=query.message.chat.id,
            message_id=query.message.message_id,
            reply_markup=reply_markup
        )
        await context.bot.answer_callback_query(query.id, text="Gruppe wurde hinzugefügt")

        public_group = await context.bot.get_chat(group_query)
        if public_group.username is None:
            member = await context.bot.get_chat_member(group_query, context.bot.id)
            if member.status != 'administrator':
                await context.bot.send_message(group_query,
                                               text="Übrigens, damit ich richtig funktioniere, muss ich als Admin in "
                                                    "dieser Gruppe mitglied sein.")
                return
        with Session(engine) as s:
            group = s.query(Groups).filter(Groups.group_id == group_query).first()
            group.group_invite_link = str(f'https://t.me/{public_group.username}')
            s.commit()
        await context.bot.send_message(group_query,
                                       text="Danke, deine Gruppe wurde angenommen und ist nun auf der DACH Liste zu "
                                            "finden.")
        logging.info(f'request accepted from {query.from_user.id}')

    if answer == "decline":
        with Session(engine) as s:
            results = s.query(Groups).filter_by(group_id=group_query).all()
            if results:
                results[0].group_deleted = True
                results[0].group_active = False
                s.commit()
        reply_markup = InlineKeyboardMarkup(
            [[InlineKeyboardButton("Abgelehnt - annehmen?", callback_data=f"release+{group_query}")]])

        await context.bot.edit_message_reply_markup(
            chat_id=query.message.chat.id,
            message_id=query.message.message_id,
            reply_markup=reply_markup
        )
        await context.bot.answer_callback_query(query.id, text="Gruppe wurde abgelehnt")
        await context.bot.send_message(group_query, text="Tut mir leid, deine Gruppe wurde abgelehnt")
        await context.bot.leave_chat(group_query)
        logging.info(f'request declined from {query.from_user.id}')

    if answer == "release":
        with Session(engine) as s:
            result = s.query(Groups).filter_by(group_id=group_query).first()
            if result:
                s.delete(result)
                s.commit()
        reply_markup = InlineKeyboardMarkup(
            [[InlineKeyboardButton("Released", callback_data="ok")]])

        await context.bot.edit_message_reply_markup(
            chat_id=query.message.chat.id,
            message_id=query.message.message_id,
            reply_markup=reply_markup
        )
        await context.bot.answer_callback_query(query.id, text="Gruppe wurde freigegeben")
        logging.info(f'group released from {query.from_user.id}')
    return


async def send_group_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    reply_text = ["**🌟 Aktiven Gruppen Liste 🌟**\n"]

    with Session(engine) as s:
        active_groups = s.query(Groups).filter(
            and_(Groups.group_active, Groups.group_invite_link != "")).order_by(Groups.group_name).all()

        for group in active_groups:
            if group.group_invite_link:
                reply_text.append(f"· [{group.group_name}]({group.group_invite_link})")

    formatted_message = "\n".join(reply_text)

    # Ensure the message doesn't exceed the maximum length allowed by Telegram
    max_length = 4096

    # If the message is too long, split it into multiple messages
    while len(formatted_message) > max_length:
        split_index = formatted_message.rfind('\n', 0, max_length)
        part_message = formatted_message[:split_index]
        formatted_message = formatted_message[split_index + 1:]
        await context.bot.send_message(update.effective_chat.id, part_message, disable_web_page_preview=True,
                                       parse_mode='Markdown')

    # Send the remaining part
    await context.bot.send_message(update.effective_chat.id, formatted_message, disable_web_page_preview=True,
                                   parse_mode='Markdown')


async def release_group(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboardMarkup = []
    with Session(engine) as s:
        deleted_groups = s.query(Groups).filter(Groups.group_deleted).all()
        for group in deleted_groups:
            keyboardMarkup.append(
                [InlineKeyboardButton(f"{group.group_name}", callback_data=f'release+{group.group_id}')])

    await context.bot.send_message(
        admin_group,
        "Welche Gruppe möchtest du freigeben?",
        reply_markup=InlineKeyboardMarkup(keyboardMarkup)
    )
    return


async def generate_new_link(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logging.info('starting generation of link >> generate_new_link')
    current_group_id = update.effective_chat.id  # Get the current group id

    with Session(engine) as s:
        group = s.query(Groups).filter(Groups.group_id == current_group_id).first()
        member = await context.bot.get_chat_member(current_group_id, context.bot.id)
        if member.status == 'administrator':
            x = await context.bot.export_chat_invite_link(current_group_id)
            group.group_invite_link = str(x)
            s.commit()
            logging.info(f'Invite link updated for {group.group_name}. New link: {group.group_invite_link}')
            await context.bot.send_message(current_group_id, "✅")
        elif member.status != 'administrator':
            public_group = await context.bot.get_chat(current_group_id)
            if public_group.username is None:
                await context.bot.send_message(current_group_id,
                                               "Um einen Link für deine Gruppe zu erzeugen, benötige ich Admin rechte.")
            else:
                group.group_invite_link = str(f'https://t.me/{public_group.username}')
                s.commit()
                logging.info(f'Invite link updated for {group.group_name}. New link: {group.group_invite_link}')
                await context.bot.send_message(current_group_id, "✅")
        else:
            logging.error(f'Invite link update for {group.group_name} failed.')
            await context.bot.send_message(current_group_id, "❌")
    return


def is_bot_admin(chat_member: ChatMember):
    return chat_member.status in {ChatMember.ADMINISTRATOR, ChatMember.OWNER}


async def status_changed(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    current_group_id = update.effective_chat.id

    if not update.my_chat_member:
        return
    if not update.my_chat_member.new_chat_member.user.is_bot:
        return

    promoted = False
    if is_bot_admin(update.my_chat_member.new_chat_member) and (
            not update.my_chat_member.old_chat_member or not is_bot_admin(update.my_chat_member.old_chat_member)):
        promoted = True
    elif update.my_chat_member.new_chat_member.status in {ChatMember.MEMBER, ChatMember.RESTRICTED} and (
            update.my_chat_member.old_chat_member or (
            update.my_chat_member.old_chat_member and is_bot_admin(update.my_chat_member.old_chat_member))):
        promoted = False
    else:
        return

    with Session(engine) as s:
        group = s.query(Groups).filter_by(group_id=current_group_id).first()
        group.is_admin = bool(promoted)
        if promoted:
            invite_link_object = await context.bot.export_chat_invite_link(current_group_id)
            group.group_invite_link = invite_link_object
        s.commit()

    return


DEVELOPER_CHAT_ID = -1002005123500


async def error_handler(update: object, context: CallbackContext) -> None:
    """Log the error and send a telegram message to notify the developer."""
    # Log the error before we do anything else, so we can see it even if something breaks.
    logger.error(msg="Exception while handling an update:", exc_info=context.error)

    # traceback.format_exception returns the usual python message about an exception, but as a
    # list of strings rather than a single string, so we have to join them together.
    tb_list = traceback.format_exception(None, context.error, context.error.__traceback__)
    tb_string = ''.join(tb_list)

    # Build the message with some markup and additional information about what happened.
    # You might need to add some logic to deal with messages longer than the 4096 character limit.
    update_str = update.to_dict() if isinstance(update, Update) else str(update)
    message = (
        f'An exception was raised while handling an update\n'
        f'<pre>update = {html.escape(json.dumps(update_str, indent=2, ensure_ascii=False))}'
        '</pre>\n\n'
        f'<pre>context.chat_data = {html.escape(str(context.chat_data))}</pre>\n\n'
        f'<pre>context.user_data = {html.escape(str(context.user_data))}</pre>\n\n'
        f'<pre>{html.escape(tb_string)}</pre>'
    )

    # Finally, send the message
    await context.bot.send_message(chat_id=DEVELOPER_CHAT_ID, text=message, parse_mode=ParseMode.HTML)


def main():
    Base.metadata.create_all(engine)

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("status", bot_status))
    app.add_handler(CommandHandler('id', get_chat_id))
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, me_invited_or_joined))
    app.add_handler(CommandHandler("group_list", send_group_list))
    app.add_handler(CallbackQueryHandler(bot_to_group_check))
    app.add_handler(CommandHandler("release", release_group))
    app.add_handler(CommandHandler("update_link", generate_new_link))
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, status_changed))
    app.add_error_handler(error_handler)

    app.run_polling()


if __name__ == "__main__":
    main()
