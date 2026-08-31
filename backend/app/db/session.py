from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings

# pool_pre_ping=True: checks a connection is still alive before handing it
# out of the pool. Cheap insurance against "server closed the connection
# unexpectedly" errors after periods of idleness.
engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
