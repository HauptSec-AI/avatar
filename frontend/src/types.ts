export type Role = "visitor" | "avatar" | "human";

export interface Message {
  id: number;
  conversation_id: string;
  conversation_name: string | null;
  role: Role;
  content: string;
  tool_calls: string[] | null;
  needs_attention: boolean;
  read: boolean;
  created_at: string;
}

export interface ConversationSummary {
  conversation_id: string;
  conversation_name: string | null;
  preview: string;
  last_role: Role;
  last_message_at: string;
  message_count: number;
  unread: boolean;
  needs_attention: boolean;
}

export interface ConfigResponse {
  owner_name: string;
}
