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
  /** 后端消息 id，仅从 /messages 拉取的消息才有；乐观更新的消息为 undefined */
  id?: number;
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
  updatedAt?: number;
  messages: Message[];
  /** messages 是否已从后端加载（用于 LRU 缓存判定） */
  loaded?: boolean;
  /** 是否还有更早的消息可加载（分页用） */
  hasMore?: boolean;
  /** 当前已加载消息中的最早 id（分页用，作为下次 before_id） */
  oldestLoadedId?: number;
  /** 是否正在加载更早的消息（分页用） */
  loadingOlder?: boolean;
}

/** SSE 事件类型 */
export type SSEEvent =
  | { type: "status"; node: string; message: string }
  | { type: "token"; content: string }
  | { type: "done"; agent_type: string; intent: string; full_answer: string; citations?: Citation[]; title?: string | null }
  | { type: "error"; message: string };
