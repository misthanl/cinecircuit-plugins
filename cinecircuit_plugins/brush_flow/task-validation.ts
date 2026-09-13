export function validIntakeTime(value: unknown): boolean {
  const text = String(value ?? "").trim();
  if (!text) return true;
  if (!/^(?:[01]\d|2[0-3]):[0-5]\d-(?:[01]\d|2[0-3]):[0-5]\d$/.test(text)) return false;
  const [start, end] = text.split("-");
  return start !== end;
}
export function validRange(value: unknown): boolean {
  const text = String(value ?? "").trim();
  if (!text) return true;
  if (!/^\d+(?:\.\d+)?(?:\s*-\s*\d+(?:\.\d+)?)?$/.test(text)) return false;
  const [low, high = low] = text.split("-").map(Number);
  return Number.isFinite(high) && low <= high;
}
function validField(field: string, low: number, high: number): boolean {
  return field.split(",").every(part => {
    if (!/^(?:\*|\d+(?:-\d+)?)(?:\/\d+)?$/.test(part)) return false;
    const [base, step = "1"] = part.split("/");
    if (Number(step) < 1) return false;
    if (base === "*") return true;
    const [start, end = start] = base.split("-").map(Number);
    return start >= low && end <= high && start <= end;
  });
}
export function validCron(value: unknown): boolean {
  const text = String(value || "").trim();
  if (!text) return true;
  const fields = text.split(/\s+/);
  const limits = [[0, 59], [0, 23], [1, 31], [1, 12], [0, 7]];
  return fields.length === 5 && fields.every((field, index) => validField(field, ...limits[index] as [number, number]));
}
