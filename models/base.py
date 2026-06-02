"""
SQLAlchemy 共享 Base
所有模型继承自此 Base，确保 metadata 统一
"""
from sqlalchemy.orm import declarative_base

Base = declarative_base()
