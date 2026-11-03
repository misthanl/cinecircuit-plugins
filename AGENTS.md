# Independent plugin repository instructions

Concrete plugin implementations and tests belong here; host-only generic contracts remain in ../cinecircuit. Preserve concurrent side-task changes.

## Release version discipline (user requirement)

- Before changing application or plugin versions, verify the latest published version from GitHub. For plugins, inspect the remote default branch's published `plugins.json` and its referenced package manifests; for the application, inspect its published source/version and release metadata. Record the verified remote commit/version in build evidence. Do not treat local build snapshots as published releases.
- Bump each affected component at most once per unpublished release batch. Repeated fixes, reviews, side-task changes, package rebuilds and image rebuilds for that batch MUST reuse its already selected target version. Only start another version increment after the preceding version is actually published, unless the user explicitly requests a different version.
- Coordinate side tasks against that same published baseline and pending target. Never calculate a new version just by incrementing the current working-tree version. If GitHub verification fails, retain the pending version and report the verification limit rather than inventing another bump.
- Keep source manifests, packaged manifests and application runtime version consistent. Preserve exact prior ZIPs for installed-version recovery. An unpublished same-version rebuild must not overwrite a published immutable package; use content-addressed artifacts and only explicit known digest replacements where the host supports them. Never infer replacement from a different hash alone or directly rewrite installed database versions.
