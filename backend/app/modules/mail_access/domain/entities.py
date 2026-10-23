from dataclasses import dataclass, field


@dataclass
class MessageSummary:
    uid: int
    subject: str
    sender: str
    date: str
    size: int
    seen: bool


@dataclass
class MessagePage:
    uid_validity: int
    total: int
    items: list[MessageSummary]


@dataclass
class MessageDetail(MessageSummary):
    recipients: str
    body: str
    attachments: list[str] = field(default_factory=list)
    truncated: bool = False
    message_id: str = ''
    reply_to: str = ''
    references: str = ''
