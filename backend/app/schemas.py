from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    conversation_id: str
    name: str | None = None
    message: str = Field(min_length=1)


class AdminLoginRequest(BaseModel):
    password: str


class AdminMessageRequest(BaseModel):
    content: str = Field(min_length=1)


class VoiceSessionRequest(BaseModel):
    conversation_id: str


class VoiceSessionStartedRequest(BaseModel):
    conversation_id: str
    elevenlabs_conversation_id: str = Field(min_length=1)


class VoiceFaqToolRequest(BaseModel):
    """Body of the faq_tool webhook call. conversation_id is OUR OWN conversation_id
    (not ElevenLabs'), populated via the SDK's `dynamicVariables` at session start
    (see voiceSession.ts) and interpolated into the webhook body by the agent's tool
    config (see voice.build_agent_config) -- a value we set ourselves end to end,
    not a guessed ElevenLabs system variable."""

    conversation_id: str = Field(min_length=1)
    question_number: int


class VoicePushToolRequest(BaseModel):
    conversation_id: str = Field(min_length=1)
    message: str = Field(min_length=1)
