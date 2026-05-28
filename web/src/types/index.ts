/** 引文条目 */
export interface Citation {
  id: number;
  source: string;
  chapter: string;
  section_title: string;
  heading_path: string;
  chunk_type: string;
  table_id: string;
  row_range: string;
}

/** 消息类型 */
export interface Message {
  role: "user" | "assistant";
  content: string;
  agentType?: string;
  intent?: string;
  citations?: Citation[];
}

/** 会话 */
export interface Session {
  id: string;
  title: string;
  createdAt: number;
  messages: Message[];
}

/** SSE 事件类型 */
export type SSEEvent =
  | { type: "status"; node: string; message: string }
  | { type: "token"; content: string }
  | { type: "done"; agent_type: string; intent: string; full_answer: string; citations?: Citation[] }
  | { type: "error"; message: string };
