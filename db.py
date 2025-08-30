from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy import create_engine

DATABASE_URL = "sqlite:///database.db"
engine = create_engine(url=DATABASE_URL, echo=True)

class Base(DeclarativeBase):
    pass

sessionLocal = sessionmaker(bind=engine, autocommit=False, expire_on_commit=True)


def init_db():
    import models
    Base.metadata.create_all(engine)