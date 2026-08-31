from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """
    Shared declarative base for every ORM model in the app.
    Alembic's env.py (added later) will import this to autogenerate
    migrations from the model metadata.
    """

    pass
