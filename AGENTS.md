# Independent plugin repository instructions

Concrete plugin implementations and tests belong here; host-only generic contracts remain in ../cinecircuit. Preserve concurrent side-task changes.

## Release version discipline (user requirement)

- Before changing application or plugin versions, verify the latest published version from GitHub. For plugins, inspect the remote default branch's published `plugins.json` and its referenced package manifests; for the application, inspect its published source/version and release metadata. Record the verified remote commit/version in build evidence. Do not treat local build snapshots as published releases.
- Bump each affected component at most once per unpublished release batch. Repeated fixes, reviews, side-task changes, package rebuilds and image rebuilds for that batch MUST reuse its already selected target version. Only start another version increment after the preceding version is actually published, unless the user explicitly requests a different version.
- Coordinate side tasks against that same published baseline and pending target. Never calculate a new version just by incrementing the current working-tree version. If GitHub verification fails, retain the pending version and report the verification limit rather than inventing another bump.
- Keep source manifests, packaged manifests and application runtime version consistent. Preserve exact prior ZIPs for installed-version recovery. An unpublished same-version rebuild must not overwrite a published immutable package; use content-addressed artifacts and only explicit known digest replacements where the host supports them. Never infer replacement from a different hash alone or directly rewrite installed database versions.

### Formal image baseline (user correction, 2026-11-13)

- For plugins shipped with CineCircuit, the baseline is the plugin version actually included in the preceding formally released application image. A GitHub package/index push, candidate image or temporary NAS deployment does not by itself complete a new release batch or authorize another version bump.
- In the v1.4.5 batch, the formal v1.4.4 subtitle baseline is 1.0.6 and the sole target is 1.0.7. Combine all side-task fixes into that target; the withdrawn 1.0.8 and unpublished 1.0.9 are not release baselines.
- Verify the formal image catalog and release evidence as well as remote repository state. Preserve immutable known package hashes for installed recovery. Version corrections must install verified packages through the host package lifecycle, never rewrite a version field alone.
