from dataclasses import dataclass
from datetime import datetime

@dataclass
class User:
    telegram_id: int
    first_name: str
    last_name: str
    birth_date: datetime
    role: str
    phone: str

