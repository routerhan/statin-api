from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import declarative_base, relationship
from werkzeug.security import check_password_hash, generate_password_hash

Base = declarative_base()


class User(Base):
    __tablename__ = "user"

    id = Column(Integer, primary_key=True)
    username = Column(String(80), unique=True, nullable=False)
    full_name = Column(String(120), nullable=False)
    # Werkzeug's default password hash (pbkdf2:sha256) is well under 255 chars.
    password_hash = Column(String(255), nullable=False)

    # Maintain bidirectional relationship with automatic cascade on delete.
    evaluations = relationship(
        "Evaluation",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    @property
    def is_guest(self) -> bool:
        return False


class Evaluation(Base):
    __tablename__ = "evaluation"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("user.id"), nullable=False)
    ck_value = Column(Float, nullable=False)
    transaminase = Column(Float, nullable=False)
    bilirubin = Column(Float, nullable=False)
    muscle_symptoms = Column(Boolean, nullable=False)
    recommendation = Column(Text, nullable=False)
    timestamp = Column(DateTime, nullable=False, server_default=func.current_timestamp())

    # Establish the many-to-one relationship back to User.
    user = relationship("User", back_populates="evaluations")
