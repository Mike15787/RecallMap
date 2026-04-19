export interface ISessionResponse {
  session_id: string;
  created_at: string;
  subject: string | null;
  exam_date: string | null;
  status: string;
}

export interface IIngestResponse {
  status: string;
  filename: string;
  chunks_added: number;
  total_chunks: number;
}

export interface IChunkPreview {
  content: string;
  source_type: string;
  source_id: string;
}
