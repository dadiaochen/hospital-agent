from typing import Annotated

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.exceptions import ResourceNotFoundError
from app.models import User


def get_demo_user(db: Annotated[Session, Depends(get_db)]) -> User:
    user = db.scalar(
        select(User).where(
            User.phone == settings.demo_user_phone,
            User.is_active.is_(True),
        )
    )
    if user is None:
        raise ResourceNotFoundError("configured demo user was not found")
    return user


DbSession = Annotated[Session, Depends(get_db)]
DemoUser = Annotated[User, Depends(get_demo_user)]
