import logging
from bot import app

from sqlalchemy.orm import Session
from sql import Groups, engine

logging.basicConfig(format='%(asctime)s %(levelname)-8s %(message)s', level=logging.INFO, datefmt='%Y-%m-%d %H:%M:%S')

async def force_update_link():
    logging.info('Force generation of links')

    with Session(engine) as s:
        groups = s.query(Groups).all()
        for group in groups:
            public_group = await app.get_chat(group.group_id)
            if public_group.username == None:
                logging.info(f'Not able to generate Link for {group.group_id} | {group.group_name}')
            else:
                group.group_invite_link = str(f'https://t.me/{public_group.username}')
                s.commit()
    return

async def main():
    await app.start()
    await force_update_link()
    await app.stop()

if __name__ == "__main__":
    app.run(main())