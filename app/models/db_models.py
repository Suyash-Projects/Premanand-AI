from sqlalchemy import Column, Integer, String, Text, ForeignKey
from sqlalchemy.orm import relationship
from app.database.connection import Base

class Video(Base):
    __tablename__ = "videos"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True)
    youtube_id = Column(String, unique=True, index=True)
    url = Column(String)

    qa_pairs = relationship("QAPair", back_populates="video", cascade="all, delete-orphan")


class QAPair(Base):
    __tablename__ = "qa_pairs"

    id = Column(Integer, primary_key=True, index=True)
    question = Column(Text, index=True)
    answer = Column(Text)
    timestamp = Column(Integer)  # Timestamp in seconds
    video_id = Column(Integer, ForeignKey("videos.id"))

    video = relationship("Video", back_populates="qa_pairs")
