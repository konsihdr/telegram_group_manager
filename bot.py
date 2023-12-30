import logging
import os
from datetime import datetime

from pyrogram import filters
from pyrogram.client import Client
from pyrogram.enums import ChatMemberStatus
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import and_
from sqlalchemy.orm import Session

from sql import Base, Groups, engine

logging.basicConfig(format='%(asctime)s %(levelname)-8s %(message)s', level=logging.INFO, datefmt='%Y-%m-%d %H:%M:%S')

if os.environ['BOT_TOKEN'] == "":
    logging.info('Not Bot Token Provided')
    exit()
else:
    bot_id = int(os.environ['BOT_TOKEN'].split(":")[0])

app = Client(
    os.environ['BOT_NAME'],
    api_id=os.environ['API_ID'],
    api_hash=os.environ['API_HASH'],
    bot_token=os.environ['BOT_TOKEN'],
    workdir="/db"
)

if os.environ['ADMIN_GROUP'] == "":
    admin_group = None
else:
    admin_group = int(os.environ['ADMIN_GROUP'])

allowed_users = list(map(int, os.environ['ALLOWED_USERS'].split(',')))


def is_bot_admin(x):
    return x.status is ChatMemberStatus.ADMINISTRATOR


@app.on_message(filters.command("start"))
async def start(c, m):
    await m.reply_text(
        f"Hi, ich bin der DACH  List Bot. Ich bin dafür da, um die DACH Gruppen zu verwalten. Wenn du mich in deiner "
        f"Gruppe hinzufügst, werde ich dir einen Link senden, mit dem du deine Gruppe auf die DACH Liste setzen "
        f"kannst. Wenn du Fragen hast, wende dich bitte an die Admins der DACH Gruppe.")


@app.on_message(filters.command("status"))
async def bot_status(c, m):
    await m.reply_text(f"{os.environ['BOT_NAME']} Online")


@app.on_message(filters.command("id"))
async def status(c, m):
    await m.reply_text(f'<pre>{m.chat.id}</pre>')


@app.on_message(filters.new_chat_members)
async def me_invited_or_joined(c, m):
    """
    Asynchroner Handler für das 'new_chat_members' Ereignis.

    Dieser Handler wird ausgelöst, wenn neue Mitglieder einem Chat beitreten.
    Es überprüft insbesondere, ob der Bot zu einer Gruppe hinzugefügt wurde.
    Wenn dies der Fall ist, wird ein Eintrag für die Gruppe in der Datenbank erstellt
    und eine Anfrage zur Genehmigung an die Admin-Gruppe gesendet.

    :param c: Der Kontext des Event-Handlers, enthält Daten zum aktuellen Zustand der Pyrogram Session.
    :param m: Das Message-Objekt, das Daten über das Ereignis enthält.
    """
    if m.new_chat_members[0].id == bot_id:
        logging.info(f'bot added to group {m.chat.title} ({m.chat.id})')
        now = datetime.now()

        with Session(engine) as s:
            group = s.query(Groups).filter_by(group_id=m.chat.id).first()
            if group:
                if group.group_deleted:
                    await app.send_message(m.chat.id, text=f"Oh Oh, deine Gruppe ist schon bekannt und es gibt ein "
                                                           f"Problem. Bitte wende dich an die Admins der DACH Gruppe."
                                                           f" Deine ID ist die {m.chat.id}")
                    await app.leave_chat(m.chat.id)
                    return
                if not group.group_deleted:
                    return
            else:
                new_group = Groups(group_name=m.chat.title, group_id=m.chat.id, group_joined=now, group_active=False,
                                   group_deleted=False, group_invite_link="")
                s.add(new_group)
                s.commit()
                await c.send_message(
                    admin_group,
                    f"Neue Gruppe Meldet sich an: {m.chat.title} ({m.chat.id})",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("Zulassen", callback_data=f'accept+{m.chat.id}'),
                        InlineKeyboardButton("Ablehnen", callback_data=f'decline+{m.chat.id}')
                    ]])
                )
        return


@app.on_callback_query()
async def bot_to_group_check(c, m):
    """
    Asynchroner Handler für das 'on_callback_query' Ereignis.

    Dieser Handler wird ausgelöst, wenn eine Callback-Abfrage empfangen wird.
    Die Funktion überprüft die Daten des Callbacks und führt je nach Dateninhalt verschiedene Aktionen aus.
    Diese können das Akzeptieren, Ablehnen oder Freigeben einer Gruppe sein. Bei jeder Aktion wird der
    Status der Gruppe in der Datenbank aktualisiert und eine Benachrichtigung an die Gruppe gesendet.

    :param c: Der Kontext des Event-Handlers, enthält Daten zum aktuellen Zustand der Pyrogram Session.
    :param m: Das CallbackQuery-Objekt, das Daten über das Callback-Ereignis enthält.
    """
    logging.info(f'got new callback {m.data}')
    logging.debug(m)

    if m.data == "ok":
        await app.answer_callback_query(m.id, text="Keine Aktion durchgeführt")
        return

    group_query = int(m.data.split('+')[1])
    answer = str(m.data.split('+')[0])

    if answer == "accept":
        with Session(engine) as s:
            results = s.query(Groups).filter_by(group_id=group_query).all()
            if results:
                results[0].group_active = True
                s.commit()
        await app.edit_message_reply_markup(
            m.message.chat.id, m.message.id,
            InlineKeyboardMarkup([[
                InlineKeyboardButton("Angenommen - ablehnen?", callback_data=f"decline+{group_query}")]]))
        await app.answer_callback_query(m.id, text="Gruppe wurde hinzugefügt")
        public_group = await app.get_chat(group_query)
        if public_group.username is None:
            member = await app.get_chat_member(group_query, "me")
            if not member.promoted_by:
                await app.send_message(group_query,
                                       text="Übrigens, damit ich richtig funktioniere, muss ich als Admin in dieser "
                                            "Gruppe mitglied sein.")
                return
        with Session(engine) as s:
            group = s.query(Groups).filter(Groups.group_id == group_query).first()
            group.group_invite_link = str(f'https://t.me/{public_group.username}')
            s.commit()
        await app.send_message(group_query,
                               text="Danke, deine Gruppe wurde angenommen und ist nun auf der DACH Liste zu finden.")
        logging.info(f'request accepted from {m.from_user.id}')
        return

    if answer == "decline":
        with Session(engine) as s:
            results = s.query(Groups).filter_by(group_id=group_query).all()
            if results:
                results[0].group_deleted = True
                results[0].group_active = False
                s.commit()
        await app.edit_message_reply_markup(
            m.message.chat.id, m.message.id,
            InlineKeyboardMarkup([[
                InlineKeyboardButton("Abgelehnt - annehmen?", callback_data=f"release+{group_query}")]]))
        await app.answer_callback_query(m.id, text="Gruppe wurde abgehlent")
        await app.send_message(group_query, text="Tut mir leid, deine Gruppe wurde abgelehnt")
        await app.leave_chat(group_query)
        logging.info(f'request declined from {m.from_user.id}')
        return

    if answer == "release":
        with Session(engine) as s:
            result = s.query(Groups).filter_by(group_id=group_query).first()
            if result:
                s.delete(result)
                s.commit()
        await app.edit_message_reply_markup(
            m.message.chat.id, m.message.id,
            InlineKeyboardMarkup([[
                InlineKeyboardButton("Angenommen - ablehnen?", callback_data=f"decline+{group_query}")]]))
        await app.answer_callback_query(m.id, text="Gruppe wurde Freigegeben")
        logging.info(f'group released from {m.from_user.id}')
        return


@app.on_message(filters.command("group_list"))
async def send_group_list(c, m):
    """
       Dieser Handler wird aktiviert, wenn der "/group_list" Befehl empfangen wird.
       Er erstellt und sendet eine Liste von aktiven Gruppennamen und deren Einladungslinks.
       Wenn die Gesamtlänge der Nachricht 4096 Zeichen (das Maximum, das von Telegram erlaubt ist) überschreitet,
       wird die Nachricht in mehrere Teile geteilt und in mehreren Nachrichten gesendet.

       :param c: Der Kontext des Handlers, enthält Daten zum aktuellen Zustand der Pyrogram Session.
       :param m: Die empfangene Nachricht, die den "/group_list" Befehl enthält.
       """
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
        await m.reply_text(part_message, disable_web_page_preview=True)

    # Send the remaining part
    await m.reply_text(formatted_message, disable_web_page_preview=True)


@app.on_message(filters.command("release"))
async def release_group(c, m):
    """
    Asynchroner Handler für den "/release" Befehl.

    Dieser Handler wird aktiviert, wenn eine Nachricht mit dem "/release" Befehl empfangen wird.
    Die Funktion zieht gelöschte Gruppen aus der Datenbank und erstellt eine Inline-Tastatur mit den
    Namen dieser Gruppen als Schaltflächen. Diese Tastatur wird dann in einer gesendeten Nachricht angezeigt,
    die fragt, welche Gruppe freigegeben werden soll.

    :param c: Der Kontext des Handlers, enthält Daten zum aktuellen Zustand der Pyrogram Session.
    :param m: Die empfangene Nachricht, die den "/group_list" Befehl enthält.
    """
    keyboardMarkup = []
    with Session(engine) as s:
        deleted_groups = s.query(Groups).filter(Groups.group_deleted).all()
        for group in deleted_groups:
            keyboardMarkup.append(
                InlineKeyboardButton(f"{group.group_name}", callback_data=f'release+{group.group_id}'))
    await c.send_message(
        admin_group,
        "Welche gruppe möchtest du Releasen?",
        reply_markup=InlineKeyboardMarkup([
            keyboardMarkup,
        ])
    )
    return


@app.on_message(filters.command("update_link"))
async def generate_new_link(c, m):
    """
    Asynchroner Handler für den "/update_link" Befehl.

    Dieser Handler wird ausgelöst, wenn eine Nachricht mit dem "/update_link" Befehl empfangen wird.
    Er aktualisiert den Einladungslink für die aktuelle Gruppe. Wenn der Bot Adminrechte in der Gruppe hat,
    erstellt er einen neuen Einladungslink. Wenn der Bot keine Adminrechte hat, aber die Gruppe öffentlich ist,
    setzt er den Einladungslink auf den Standard-Telegram-Pfad für öffentliche Gruppen.
    Die Ergebnisse werden in der Datenbank gespeichert.

    :param c: Der Kontext des Handlers, enthält Daten zum aktuellen Zustand der Pyrogram Session.
    :param m: Die empfangene Nachricht, die den "/update_link" Befehl enthält.
    """
    logging.info('starting generation of link >> generate_new_link')
    current_group_id = m.chat.id  # Get the current group id

    with Session(engine) as s:
        group = s.query(Groups).filter(Groups.group_id == current_group_id, ).first()
        member = await app.get_chat_member(current_group_id, "me")
        if member.promoted_by:
            x = await app.create_chat_invite_link(current_group_id)
            group.group_invite_link = str(x.invite_link)
            s.commit()
            logging.info(f'Invite link updated for {group.group_name}. New link: {group.group_invite_link}')
            await m.reply_text("✅")
        elif not member.promoted_by:
            public_group = await app.get_chat(current_group_id)
            if public_group.username is None:
                await m.reply_text("Um einen Link für deine Gruppe zu erzeugen, benötige ich Admin rechte.")
            else:
                group.group_invite_link = str(f'https://t.me/{public_group.username}')
                s.commit()
                logging.info(f'Invite link updated for {group.group_name}. New link: {group.group_invite_link}')
                await m.reply_text("✅")
        else:
            logging.error(f'Invite link update for {group.group_name}.')
            await m.reply_text("❌")

    return


@app.on_chat_member_updated()
async def status_changed(c, m):
    """
    Asynchroner Handler für das 'on_chat_member_updated' Ereignis.

    Dieser Handler wird ausgelöst, wenn sich der Status eines Mitglieds in einem Chat ändert.
    Insbesondere überwacht es, ob der Bot zum Administrator befördert oder von den Administratorrechten entfernt wurde.
    Bei einer Beförderung erstellt der Bot einen neuen Einladungslink für die Gruppe und speichert ihn in der Datenbank.
    Wenn der Bot seine Administratorrechte verliert, wird der Status in der Datenbank entsprechend aktualisiert.

    :param c: Der Kontext des Event-Handlers, enthält Daten zum aktuellen Zustand der Pyrogram Session.
    :param m: Das ChatMemberUpdated-Objekt, das Daten über das Ereignis enthält.
    """
    current_group_id = m.chat.id

    if not m.new_chat_member:
        return
    if not m.new_chat_member.user.is_self:
        return
    if is_bot_admin(m.new_chat_member) and (not m.old_chat_member or not is_bot_admin(m.old_chat_member)):
        promoted = True
        logging.info(f'Bot Status changed {current_group_id} >> ADMIN = {promoted}')
    elif m.new_chat_member.status in {ChatMemberStatus.MEMBER, ChatMemberStatus.RESTRICTED} and (
            m.old_chat_member or (m.old_chat_member and is_bot_admin(m.old_chat_member))):
        promoted = False
        logging.info(f'Bot Status changed {current_group_id} >> ADMIN = {promoted}')
    else:
        return

    with Session(engine) as s:
        group = s.query(Groups).filter_by(group_id=m.chat.id).first()
        group.is_admin = bool(promoted)
        if promoted:
            invite_link_object = await app.create_chat_invite_link(current_group_id)
            group.group_invite_link = invite_link_object.invite_link
        s.commit()
        return


if __name__ == "__main__":
    logging.info("Bot is Online")
    Base.metadata.create_all(engine)
    app.run()
