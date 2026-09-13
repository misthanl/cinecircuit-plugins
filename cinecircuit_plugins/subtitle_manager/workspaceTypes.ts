export interface SubtitleFile {
  name: string;
  size?: number;
}
export interface MediaIdentity {
  title?: string;
  english_title?: string;
  original_title?: string;
  aliases?: string[];
  year?: number;
  media_type?: string;
  season?: number;
  episode?: number;
  tmdb_id?: string;
  imdb_id?: string;
  douban_id?: string;
  warnings?: string[];
}
export interface MediaItem {
  path: string;
  title?: string;
  subtitles?: SubtitleFile[];
  identity?: MediaIdentity;
  poster_url?: string;
}
export interface SourceError {
  kind: string;
  message: string;
}
export interface SourceStatus {
  provider: string;
  state: string;
  candidate_count: number;
  raw_candidate_count?: number;
  errors?: SourceError[];
}
export interface OnlineSubtitle {
  title: string;
  provider: string;
  language?: string;
  format?: string;
  url?: string;
  candidate_handle: string;
  score?: number;
  match_reason?: string;
  tags?: string[];
  downloadable?: boolean;
}
export interface ManualAction {
  provider: string;
  url: string;
  reason: string;
}
export interface CaptchaChallenge {
  handle: string;
  provider: string;
  site: string;
  image?: string;
  instruction?: string;
}
export interface OnlineResponse {
  identity: MediaIdentity;
  items?: OnlineSubtitle[];
  sources?: SourceStatus[];
  manual_actions?: ManualAction[];
  captcha_challenges?: CaptchaChallenge[];
}
export interface PreviewItem {
  index: number;
  name: string;
  language: string;
  format: string;
  bytes: number;
  excerpt: string;
}
export interface PreviewResponse {
  preview_handle: string;
  items?: PreviewItem[];
  captcha_required?: boolean;
  captcha?: CaptchaChallenge;
  candidate_handle?: string;
}
export interface ItemList<T> {
  items?: T[];
}
export interface AdjustmentResult {
  adjusted_count?: number;
}
export type Requester = <T = unknown>(path: string, init?: RequestInit) => Promise<T>;

