import time
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from routers.api import Base

import os
from dotenv import load_dotenv
load_dotenv()

# DB access credentials
DB_USER = os.getenv("MYSQL_USER")
DB_PASSWORD = os.getenv("MYSQL_PASSWORD")
DB_NAME = os.getenv("MYSQL_DATABASE")
DB_HOST = "db"

if os.getenv("ENV") == "development":
    DB_USER = "root"
    DB_URL = f"mysql+pymysql://{DB_USER}@{DB_HOST}:3306/{DB_NAME}?charset=utf8"
elif os.getenv("ENV") == "production":
    DB_URL = f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:3306/{DB_NAME}?charset=utf8"

engine = create_engine(DB_URL, echo=True)

def wait_for_db_connection(max_retries=5, wait_interval=5):
    retries = 0
    while retries < max_retries:
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            print("Database connection successful")
            return True
        except OperationalError:
            retries += 1
            print(f"Database connection failed. Retrying in {wait_interval} seconds...")
            time.sleep(wait_interval)
    print("Could not connect to the database. Exiting.")
    return False

def reset_database():
    if wait_for_db_connection():
        # Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        print("Database reset successful.")
    else:
        print("Failed to reset the database due to connection issues.")

if __name__ == "__main__":
    reset_database()
