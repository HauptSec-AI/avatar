from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    conversation_id: str
    name: str | None = None
    message: str = Field(min_length=1)


class AdminLoginRequest(BaseModel):
    password: str


class AdminMessageRequest(BaseModel):
    content: str = Field(min_length=1)
