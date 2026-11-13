export function formatSize(size = 0) {
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${Math.max(1, Math.round(size / 1024))} KB`;
  return `${(size / 1024 / 1024).toFixed(1)} MB`;
}
export function subtitleFormat(name: string) {
  return name.split(".").pop()?.toUpperCase() || "字幕";
}
export function subtitleLanguage(name: string) {
  const value = name.toLowerCase();
  if (/zh[-_.]?(tw|hant)|cht/.test(value)) return "繁体中文";
  if (/zh[-_.]?(cn|hans)|chs/.test(value)) return "简体中文";
  if (/(^|[._-])en(g)?([._-]|$)/.test(value)) return "英语";
  return "自动识别";
}
