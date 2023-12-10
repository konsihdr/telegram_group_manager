import logging
import os
from datetime import datetime

from pyrogram import filters
from pyrogram.client import Client
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from pyrogram.enums import ChatMemberStatus
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_
from sql import Base, Groups, engine

logging.basicConfig(format='%(asctime)s %(levelname)-8s %(message)s', level=logging.INFO, datefmt='%Y-%m-%d %H:%M:%S')

app = Client(
    os.environ['BOT_NAME'],
    api_id=os.environ['API_ID'],
    api_hash=os.environ['API_HASH'],
    bot_token=os.environ['BOT_TOKEN'],
    workdir="/db"
)

if os.environ['BOT_TOKEN'] == "":
    logging.info('Not Bot Token Provided')
else:
    bot_id=int(os.environ['BOT_TOKEN'].split(":")[0])

if os.environ['ADMIN_GROUP'] == "":
    admin_group=None
else:
    admin_group=int(os.environ['ADMIN_GROUP'])

allowed_users = list(map(int, os.environ['ALLOWED_USERS'].split(',')))

is_bot_admin = lambda x: x.status is ChatMemberStatus.ADMINISTRATOR

@app.on_message(filters.command("start"))
async def start(c, m):
    await m.reply_text(f"Hi, ich bin der DACH  List Bot. Ich bin dafür da, um die DACH Gruppen zu verwalten. Wenn du mich in deiner Gruppe hinzufügst, werde ich dir einen Link senden, mit dem du deine Gruppe auf die DACH Liste setzen kannst. Wenn du Fragen hast, wende dich bitte an die Admins der DACH Gruppe.")

@app.on_message(filters.command("status"))
async def bot_status(c, m):
    await m.reply_text(f"{os.environ['BOT_NAME']} Online")

@app.on_message(filters.command("id"))
async def status(c, m):
    await m.reply_text(f'<pre>{m.chat.id}</pre>')

@app.on_message(filters.new_chat_members)
async def me_invited_or_joined(c, m):
    if m.new_chat_members[0].id == bot_id:
        logging.info(f'bot added to group {m.chat.title} ({m.chat.id})')
        now = datetime.now()

        with Session(engine) as s:
            group = s.query(Groups).filter_by(group_id=m.chat.id).first()
            if group:
                if group.group_deleted == True:
                    await app.send_message(m.chat.id, text=f"Oh Oh, deine Gruppe ist schon bekannt und es gibt ein Problem. Bitte wende dich an die Admins der DACH Gruppe. Deine ID ist die {m.chat.id}")
                    await app.leave_chat(m.chat.id)
                    return
                if group.group_deleted == False:
                    return
            else:
                new_group = Groups(group_name=m.chat.title, group_id=m.chat.id, group_joined=now, group_active=False, group_deleted=False, group_invite_link="")
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
        await app.send_message(group_query, text="Danke, deine Gruppe wurde angenommen und ist nun auf der DACH Liste zu finden.")
        member = await app.get_chat_member(group_query, "me")
        if not member.promoted_by:
            await app.send_message(group_query, text="Übrigens, damit ich richtig funktioniere, muss ich als Admin in dieser Gruppe mitglied sein. Danke!")
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
                InlineKeyboardButton("Abgehlent - annehmen?", callback_data=f"release+{group_query}")]]))
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
    reply_text = ["**🌟 Aktiven Gruppen Liste 🌟**\n"]
    
    with Session(engine) as s:
        active_groups = s.query(Groups).filter(and_(Groups.group_active == True, Groups.group_invite_link != "")).order_by(Groups.group_name).all()
        
        for group in active_groups:
            if group.group_invite_link:
                reply_text.append(f"· [{group.group_name}]({group.group_invite_link})")

    formatted_message = "\n".join(reply_text)

    # Ensure the message doesn't exceed the maximum length allowed by Telegram
    max_length = 4096
    #TODO: seperate message if too long
    if len(formatted_message) > max_length:
        formatted_message = formatted_message[:max_length] + "\n..."

    await m.reply_text(formatted_message, disable_web_page_preview=True)


@app.on_message(filters.command("release"))
async def release_group(c, m):
    keyboardMarkup = []
    with Session(engine) as s:
        deleted_groups = s.query(Groups).filter(Groups.group_deleted == True).all()
        for group in deleted_groups:
            keyboardMarkup.append(InlineKeyboardButton(f"{group.group_name}", callback_data=f'release+{group.group_id}'))
    await c.send_message(
        admin_group, 
        "Welche gruppe möchtest du Releasen?",
        reply_markup=InlineKeyboardMarkup([
            keyboardMarkup,
        ])
    )
    return

@app.on_message(filters.command("info") and filters.user(allowed_users))
async def send_info_to_groups(c, m):
    logging.info(f'New Info message send by {m.from_user.first_name} - {m.from_user.id}')
    info_text = m.text
    info_text = info_text.replace("/info", "")
    with Session(engine) as s:
        active_groups = s.query(Groups).filter(Groups.group_active == True).order_by(Groups.group_name).all()
        for group in active_groups:
            await app.send_message(group.group_id, info_text)
    return

@app.on_message(filters.command("update_link"))
async def generate_new_link(c, m):
    logging.info('starting generation of link >> generate_new_link')
    current_group_id = m.chat.id  # Get the current group id

    with Session(engine) as s:
        group = s.query(Groups).filter(
            Groups.group_id == current_group_id,
            or_(Groups.group_invite_link == "", Groups.group_invite_link.is_(None))
        ).first()

        if group:
            logging.info(f'checking link for {group.group_name} {group.group_id}')
            member = await app.get_chat_member(current_group_id, "me")
            if member.promoted_by:
                x = await app.create_chat_invite_link(current_group_id)
                group.group_invite_link = str(x.invite_link)
                s.commit()
                logging.info(f'Invite link updated for {group.group_name}. New link: {group.group_invite_link}')
            else:
                await app.send_message(current_group_id, text="Damit ich einen Invite Link für deine Gruppe erzeugen kann, benötige ich Adminrechte. Bitte füge mich als Admin hinzu.")
        else:
            logging.info(f'Group {current_group_id} not found or already has an invite link')
            await app.send_message(current_group_id, text="Ich habe keine Gruppe mit dieser ID gefunden oder es gibt bereits einen Invite Link. Bitte wende dich an die Admins der DACH Gruppe.")

    return


@app.on_chat_member_updated()
async def status_changed(c, m):
    current_group_id = m.chat.id
    
    if not m.new_chat_member: return
    if not m.new_chat_member.user.is_self: return 
    if is_bot_admin(m.new_chat_member) and (not m.old_chat_member or not is_bot_admin(m.old_chat_member)):
        promoted = True
        invite_link_object = await app.create_chat_invite_link(current_group_id)
        logging.info(f'Bot Status changed {current_group_id} >> ADMIN = {promoted}')
    elif m.new_chat_member.status in {ChatMemberStatus.MEMBER, ChatMemberStatus.RESTRICTED} and (m.old_chat_member or (m.old_chat_member and is_bot_admin(m.old_chat_member))):
        promoted = False
        logging.info(f'Bot Status changed {current_group_id} >> ADMIN = {promoted}')
    else: return

    with Session(engine) as s:
        group = s.query(Groups).filter_by(group_id=m.chat.id).first()
        group.is_admin = bool(promoted)
        if promoted:
            group.group_invite_link = invite_link_object.invite_link
        s.commit()
        return


if __name__ == "__main__":
    logging.info("Bot is Online")
    print(allowed_users)
    print(type(allowed_users))
    Base.metadata.create_all(engine)
    app.run()