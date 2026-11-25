# Independent plugin repository instructions

Concrete plugin implementations and tests belong here; host-only generic contracts remain in ../cinecircuit. Preserve concurrent side-task changes.

## Release version discipline (user requirement)

- Plugin versions MUST use the versions actually included in the most recent formally published application image as their baseline. Verify that image's immutable digest, pinned plugin catalog commit, package manifests and hashes, and record this evidence before choosing target versions. A GitHub package/index push, source commit, candidate image, temporary NAS deployment or moving `latest` tag alone is not a new release baseline. For application versions, also verify the published source/version and release metadata.
- Each changed plugin receives exactly one version increment per release batch; unchanged plugins keep their released versions and packages. Repeated fixes, reviews, side-task changes, package rebuilds and image rebuilds MUST reuse that batch's selected target version. Never increment again merely because code changed or an intermediate package was pushed.
- A batch becomes the next plugin-version baseline only after its image is actually formally published and verified to contain those plugin versions. Until then, continue the same batch and target versions. An explicit user instruction may override a target version.
- Coordinate every side task against the same verified image baseline and pending targets. Never increment from the current working-tree version or the repository index alone. If the published image/catalog cannot be verified, retain any pending target and report the missing evidence rather than inventing another bump.
- Keep source manifests, packaged manifests and application runtime version consistent. Preserve exact prior ZIPs for installed-version recovery. An unpublished same-version rebuild must not overwrite a published immutable package; use content-addressed artifacts and only explicit known digest replacements where the host supports them. Never infer replacement from a different hash alone or directly rewrite installed database versions.

- Version corrections must install verified packages through the host package lifecycle, never rewrite a version field alone.
