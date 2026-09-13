# Plugin form presentation

The host renders generic controls; plugins own presentation choices in
`manifest.config_schema`. These options require a host with form-presentation
support. Older hosts ignore the additional keys and retain their prior layout
and hint behavior; backend settings and validation are unchanged.

```json
{
  "editor_width": 920,
  "description_display": "hidden",
  "layout": { "columns": 2, "row_gap": 14, "column_gap": 16 },
  "sections": [{ "key": "output", "title": "Output", "icon": "mdi-image-outline" }],
  "fields": [{
    "key": "duration",
    "section": "output",
    "input_type": "number",
    "label": "Duration",
    "description": "Output duration in seconds",
    "description_display": "always",
    "validation": { "minimum": 2 }
  }]
}
```

- `description_display`: `hidden`, `always`, or `auto` (legacy behavior).
  Field declarations override the schema default. `compact` controls density,
  not whether descriptions exist. Error messages remain visible.
- `layout`: desktop columns (integer 1–4), row/column gaps (integer 8–32 px).
  With layout opted in, invalid/missing values use public defaults. Mobile
  remains one column. Without a layout declaration, existing page columns remain
  unchanged. `SchemaFields` also accepts a `layout` prop for any consuming page.
- Section `icon` overrides the compatibility default; an empty string hides it.
- Field order, labels, defaults, options, validation, visibility and spans remain
  field-schema responsibilities. Width uses the existing `editor_width` option.
- Custom editors should use the SDK `SchemaFields` component, forwarding the
  supplied field descriptors unchanged. `plugin-config-grid` opts into shared
  field spacing/typography, not column count. `app-form-layout` explicitly opts
  into the parameterized columns and the 760px breakpoint. Both consume inherited
  layout tokens. A local single-column region can declare
  `--app-plugin-config-columns: 1` without changing its siblings. Custom editors
  retain responsibility for business controls.
- Statistics use the existing `plugin.statistics` contribution. Shared dialog
  headers, accessible controls, fonts and button styles remain host primitives;
  plugin-specific content, actions and layout stay in the plugin package.

Changing these declarations after the supporting host is deployed requires
repackaging the plugin, not changing the host. No plugin IDs belong in host
presentation logic.
