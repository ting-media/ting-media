"""
State Manager for storing and retrieving data
Uses SQLite for persistence
"""
from sqlalchemy import create_engine, Column, String, Text, DateTime, Integer, Boolean, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import json

from config import DATABASE_URL

Base = declarative_base()
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)

class Message(Base):
    __tablename__ = "messages"

    id = Column(String, primary_key=True)
    platform = Column(String)  # "whatsapp" or "gmail"
    platform_id = Column(String)  # Message ID in platform
    sender = Column(String)
    sender_id = Column(String)
    content = Column(Text)
    timestamp = Column(DateTime)
    received_time = Column(DateTime)  # When we fetched it
    response_time_minutes = Column(Float, nullable=True)
    is_read = Column(Boolean, default=False)
    extra_data = Column(Text)  # JSON extra data

class Task(Base):
    __tablename__ = "tasks"

    id = Column(String, primary_key=True)
    title = Column(String)
    description = Column(Text)
    source_message_id = Column(String)  # Original message that created it
    platform = Column(String)  # whatsapp or gmail
    status = Column(String, default="open")  # open, in_progress, completed
    priority = Column(String, default="normal")  # low, normal, high, urgent
    created_at = Column(DateTime)
    updated_at = Column(DateTime)
    due_date = Column(DateTime, nullable=True)
    assigned_to = Column(String, nullable=True)
    extra_data = Column(Text)  # JSON

class TaskLink(Base):
    __tablename__ = "task_links"

    id = Column(String, primary_key=True)
    task_id_1 = Column(String)
    task_id_2 = Column(String)
    link_type = Column(String)  # "duplicate", "related", "dependent"
    confidence = Column(Float)  # 0-1 confidence score
    created_at = Column(DateTime)

class SyncRun(Base):
    __tablename__ = "sync_runs"

    id = Column(String, primary_key=True)
    start_time = Column(DateTime)
    end_time = Column(DateTime, nullable=True)
    messages_fetched = Column(Integer, default=0)
    tasks_created = Column(Integer, default=0)
    status = Column(String)  # running, completed, error

# Create tables
Base.metadata.create_all(engine)

class StateManager:
    def __init__(self):
        self.session = SessionLocal()

    def add_message(self, message_dict: Dict) -> str:
        """Add a message to DB"""
        msg_id = message_dict.get('id')

        # Check if already exists
        existing = self.session.query(Message).filter(Message.id == msg_id).first()
        if existing:
            return msg_id

        msg = Message(
            id=msg_id,
            platform=message_dict.get('platform'),
            platform_id=message_dict.get('platform_id', msg_id),
            sender=message_dict.get('sender'),
            sender_id=message_dict.get('sender_id'),
            content=message_dict.get('content'),
            timestamp=message_dict.get('timestamp', datetime.now()),
            received_time=datetime.now(),
            response_time_minutes=message_dict.get('response_time_minutes'),
            extra_data=json.dumps(message_dict.get('metadata', {}))
        )

        self.session.add(msg)
        self.session.commit()

        return msg_id

    def add_task(self, task_dict: Dict) -> str:
        """Add a task to DB"""
        task_id = task_dict.get('id')

        task = Task(
            id=task_id,
            title=task_dict.get('title'),
            description=task_dict.get('description'),
            source_message_id=task_dict.get('source_message_id'),
            platform=task_dict.get('platform'),
            status=task_dict.get('status', 'open'),
            priority=task_dict.get('priority', 'normal'),
            created_at=datetime.now(),
            updated_at=datetime.now(),
            due_date=task_dict.get('due_date'),
            assigned_to=task_dict.get('assigned_to'),
            extra_data=json.dumps(task_dict.get('metadata', {}))
        )

        self.session.add(task)
        self.session.commit()

        return task_id

    def link_tasks(self, task_id_1: str, task_id_2: str, link_type: str = "related", confidence: float = 1.0) -> str:
        """Link two tasks together"""
        link_id = f"{task_id_1}_{task_id_2}"

        link = TaskLink(
            id=link_id,
            task_id_1=task_id_1,
            task_id_2=task_id_2,
            link_type=link_type,
            confidence=confidence,
            created_at=datetime.now()
        )

        self.session.add(link)
        self.session.commit()

        return link_id

    def get_recent_messages(self, hours: int = 1, platform: Optional[str] = None) -> List[Dict]:
        """Get messages from last N hours"""
        since = datetime.now() - timedelta(hours=hours)

        query = self.session.query(Message).filter(Message.timestamp >= since)
        if platform:
            query = query.filter(Message.platform == platform)

        messages = query.all()

        return [self._message_to_dict(m) for m in messages]

    def get_open_tasks(self, platform: Optional[str] = None) -> List[Dict]:
        """Get all open tasks"""
        query = self.session.query(Task).filter(Task.status.in_(["open", "in_progress"]))
        if platform:
            query = query.filter(Task.platform == platform)

        tasks = query.all()

        return [self._task_to_dict(t) for t in tasks]

    def get_linked_tasks(self, task_id: str) -> List[Dict]:
        """Get all tasks linked to a task"""
        links = self.session.query(TaskLink).filter(
            (TaskLink.task_id_1 == task_id) | (TaskLink.task_id_2 == task_id)
        ).all()

        linked_tasks = []
        for link in links:
            other_id = link.task_id_2 if link.task_id_1 == task_id else link.task_id_1
            task = self.session.query(Task).filter(Task.id == other_id).first()
            if task:
                linked_tasks.append({
                    'task': self._task_to_dict(task),
                    'link_type': link.link_type,
                    'confidence': link.confidence
                })

        return linked_tasks

    def update_task_status(self, task_id: str, status: str):
        """Update task status"""
        task = self.session.query(Task).filter(Task.id == task_id).first()
        if task:
            task.status = status
            task.updated_at = datetime.now()
            self.session.commit()

    def get_analytics(self, hours: int = 24) -> Dict:
        """Get analytics for last N hours"""
        since = datetime.now() - timedelta(hours=hours)

        messages = self.session.query(Message).filter(Message.timestamp >= since).all()
        tasks = self.session.query(Task).filter(Task.created_at >= since).all()

        response_times = [m.response_time_minutes for m in messages if m.response_time_minutes]

        return {
            'total_messages': len(messages),
            'messages_by_platform': {
                'whatsapp': len([m for m in messages if m.platform == 'whatsapp']),
                'gmail': len([m for m in messages if m.platform == 'gmail'])
            },
            'total_tasks': len(tasks),
            'open_tasks': len([t for t in tasks if t.status == 'open']),
            'in_progress_tasks': len([t for t in tasks if t.status == 'in_progress']),
            'completed_tasks': len([t for t in tasks if t.status == 'completed']),
            'avg_response_time_minutes': sum(response_times) / len(response_times) if response_times else 0,
            'high_priority_tasks': len([t for t in tasks if t.priority in ['high', 'urgent']])
        }

    def _message_to_dict(self, msg: Message) -> Dict:
        """Convert Message object to dict"""
        return {
            'id': msg.id,
            'platform': msg.platform,
            'sender': msg.sender,
            'content': msg.content,
            'timestamp': msg.timestamp.isoformat() if msg.timestamp else None,
            'response_time_minutes': msg.response_time_minutes,
            'metadata': json.loads(msg.extra_data) if msg.extra_data else {}
        }

    def _task_to_dict(self, task: Task) -> Dict:
        """Convert Task object to dict"""
        return {
            'id': task.id,
            'title': task.title,
            'description': task.description,
            'platform': task.platform,
            'status': task.status,
            'priority': task.priority,
            'created_at': task.created_at.isoformat() if task.created_at else None,
            'due_date': task.due_date.isoformat() if task.due_date else None,
            'assigned_to': task.assigned_to,
            'metadata': json.loads(task.extra_data) if task.extra_data else {}
        }

    def close(self):
        """Close database session"""
        self.session.close()
