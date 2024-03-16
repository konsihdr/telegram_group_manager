import datetime
#import os

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

#connection_string = f"mysql+mysqlconnector://{os.environ['DATABASE_USERNAME']}:{os.environ['DATABASE_PASSWORD']}@{os.environ['DATABASE_HOST']}:3306/{os.environ['DATABASE']}"
#engine = create_engine(connection_string)
engine = create_engine("sqlite:////db/GROUP_MANAGER.db")

class Base(DeclarativeBase):
    pass

class Groups(Base):
    __tablename__ = "groups"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    group_name: Mapped[str]
    group_id: Mapped[int]
    group_joined: Mapped[datetime.datetime]
    group_active: Mapped[bool]
    group_deleted: Mapped[bool]
    group_invite_link: Mapped[str] = mapped_column(nullable=True)
    last_invite_check: Mapped[datetime.datetime] = mapped_column(nullable=True)
    is_admin: Mapped[bool] = mapped_column(nullable=True, default=False)

if __name__ == "__main__":
    Base.metadata.create_all(engine)
