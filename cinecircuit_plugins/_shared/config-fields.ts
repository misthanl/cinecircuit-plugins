export interface ConfigField {
  key: string;
  label?: string;
  input_type?: string;
  disabled?: boolean;
  [key: string]: unknown;
}

/** Keep the manifest as the source of labels, defaults, options and validation. */
export function orderedFields(fields: ConfigField[], order: string[]): ConfigField[] {
  return order.flatMap(key => {
    const field = fields.find(candidate => candidate.key === key);
    return field ? [{ ...field }] : [];
  });
}
