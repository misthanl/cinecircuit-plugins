# Source and license

Protocol and behavior reference: MoviePilot IYUUAutoSeed / IyuuHelper by jxxghp
and CKun, GPL-3.0.
https://github.com/jxxghp/MoviePilot-Plugins/tree/87cd6a72d6e7991a8c32c1fea654b4c63b246c8f/plugins.v2/iyuuautoseed

This is a modified CC adaptation, distributed under GPL-3.0-only, with the full
license included in the installation archive. MoviePilot classes and internal
services are replaced by the public CC SDK.

All 19 upstream configuration capabilities are represented. `notify` is named
`notification_enabled`. Site authentication and torrent bytes stay in CC; the
plugin receives opaque references and safe file metadata. Failed batches are
isolated, transient errors retry, permanent 404/410 results can be cleared, and
caches have a 10000-entry budget per namespace. Random tags are not generated.
Brush-flow sources are excluded in this first release.
