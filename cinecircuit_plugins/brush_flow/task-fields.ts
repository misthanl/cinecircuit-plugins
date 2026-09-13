import type { ConfigField } from "../_shared/config-fields";
export const basicFields: ConfigField[] = [
  { key: "enabled", label: "启用此任务", input_type: "switch", default: true },
  { key: "notification_enabled", label: "发送任务执行通知", input_type: "switch", default: false },
  { key: "name", label: "任务名称", input_type: "text" },
  { key: "save_path", label: "保存目录", input_type: "text" },
];
export const limitFields: ConfigField[] = [
  { key: "max_add", label: "每次最多添加", input_type: "number", default: 3, validation: { minimum: 1 } },
  { key: "task_limit", label: "本任务下载数量上限", input_type: "number", default: 0, validation: { minimum: 0 } },
  { key: "upload_limit_kib", label: "单种上传限速（KiB/s）", input_type: "number", default: 0, validation: { minimum: 0 } },
  { key: "download_limit_kib", label: "单种下载限速（KiB/s）", input_type: "number", default: 0, validation: { minimum: 0 } },
  { key: "seeding_limit_gib", label: "保种总体积上限（GiB）", input_type: "number", default: 0, validation: { minimum: 0 } },
];
export const selectionFields: ConfigField[] = [
  { key: "promotion", label: "促销", input_type: "select", default: "free", options: [{ value: "all", label: "全部（包括普通）" }, { value: "free", label: "免费" }, { value: "2xfree", label: "2X 免费" }] },
  { key: "exclude_hr", label: "排除 H&R", input_type: "select", default: true, options: [{ value: true, label: "是" }, { value: false, label: "否" }] },
  { key: "use_rss", label: "使用 RSS", input_type: "switch", default: false },
  { key: "site_hr", label: "全站 H&R", input_type: "switch", default: false },
  { key: "exclude_subscriptions", label: "排除订阅", input_type: "switch", default: false },
  { key: "size_range", label: "种子大小（GB）", input_type: "text", placeholder: "0-100" },
  { key: "seeders_range", label: "做种人数", input_type: "text", placeholder: "0-100" },
  { key: "publish_range", label: "发布时间（分钟）", input_type: "text", placeholder: "0-100" },
  { key: "include", label: "包含规则（正则）", input_type: "text" },
  { key: "exclude", label: "排除规则（正则）", input_type: "text" },
];
export const deletionFields: ConfigField[] = [
  { key: "delete_ratio", label: "分享率达到后处理", input_type: "number", validation: { minimum: 0 } },
  { key: "delete_seed_hours", label: "做种小时达到后处理", input_type: "number", validation: { minimum: 0 } },
  { key: "delete_upload_gib", label: "上传量达到后处理（GiB）", input_type: "number", validation: { minimum: 0 } },
  { key: "delete_download_hours", label: "下载时长达到后处理（小时）", input_type: "number", validation: { minimum: 0 } },
  { key: "delete_inactive_hours", label: "未活动时间达到后处理（小时）", input_type: "number", validation: { minimum: 0 } },
  { key: "delete_avg_upload_kib", label: "平均上传速度低于时处理（KiB/s）", input_type: "number", validation: { minimum: 0 } },
  { key: "delete_expired_promotion", label: "删除促销过期的未完成下载", input_type: "switch", default: false },
  { key: "exclude_tags", label: "排除标签", input_type: "text", default: "CineCircuit,H&R", placeholder: "多个标签用逗号分隔" },
];
export const executionFields: ConfigField[] = [
  { key: "intake_time_range", label: "进种时间段", input_type: "text", default: "", placeholder: "00:00-08:00，留空全天（北京时间）" },
  { key: "interval_minutes", label: "刷流刷新周期（分钟）", input_type: "number", default: 10, validation: { minimum: 1 } },
  { key: "check_interval_minutes", label: "状态检查周期（分钟）", input_type: "number", default: 5, validation: { minimum: 1 } },
  { key: "cron", label: "Cron 执行周期（可选）", input_type: "cron" },
];
