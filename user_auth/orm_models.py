# user_auth/orm_models.py
from sqlalchemy import create_engine, Column, Integer, String, Text, Index
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.dialects.sqlite import JSON # For profile_data if we treat it as JSON

Base = declarative_base()

class UserProfile(Base):
    __tablename__ = "user_auth_profiles"

    user_id = Column(String, primary_key=True, index=True)
    display_name = Column(String, nullable=False)
    email = Column(String, index=True, nullable=True)
    aad_object_id = Column(String, index=True, nullable=True)
    tenant_id = Column(String, nullable=True)
    assigned_role = Column(String, nullable=False, default='DEFAULT', index=True)
    first_seen_timestamp = Column(Integer, nullable=False)
    last_active_timestamp = Column(Integer, nullable=False)
    profile_data = Column(Text, nullable=True) # Storing as Text, can be loaded as JSON in application logic
    profile_version = Column(Integer, nullable=False, default=1)

    # Defining indexes explicitly (though some are created by index=True above)
    # This is more for visibility and consistency with the existing DDL if specific index names are desired.
    # SQLAlchemy will typically create indexes named like ix_tablename_columnname
    __table_args__ = (
        Index('idx_user_email', 'email'),
        Index('idx_user_aad_object_id', 'aad_object_id'),
        Index('idx_user_assigned_role', 'assigned_role'),
    )

    def __repr__(self):
        return (
            f"<UserProfile(user_id='{self.user_id}', display_name='{self.display_name}', "
            f"email='{self.email}', assigned_role='{self.assigned_role}')>"
        )

# Example of how to set up the engine (usually done in a central place like config or main app setup)
# from config import get_config
# def get_engine():
#     db_path = get_config().STATE_DB_PATH
#     # The path needs to be prefixed with 'sqlite:///' for SQLAlchemy
#     # If db_path is an absolute Windows path (e.g., C:\path\to\db.sqlite),
#     # it becomes 'sqlite:///C:\path\to\db.sqlite'.
#     # If it's a relative path (e.g., db/state.sqlite), it becomes 'sqlite:///db/state.sqlite'.
#     engine = create_engine(f"sqlite:///{db_path}")
#     Base.metadata.create_all(engine) # This would create tables if they don't exist based on ORM models
#     return engine

# def get_session(engine):
#     Session = sessionmaker(bind=engine)
#     return Session() 