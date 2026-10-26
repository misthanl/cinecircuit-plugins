# Source and license

Behavior reference: MoviePilot TorrentTransfer by jxxghp.
https://github.com/jxxghp/MoviePilot-Plugins/tree/87cd6a72d6e7991a8c32c1fea654b4c63b246c8f/plugins.v2/torrenttransfer

The CC implementation uses the independent plugin SDK and is distributed under
GPL-3.0-only. The full license is included in the installation archive.

All 21 upstream configuration capabilities are represented. `notify` is named
`notification_enabled` to use CC's existing notification switch. Torrent files
are exported by API where possible, with a read-only directory fallback.
Source removal waits until the target is complete; it never deletes data files.
Random task tags are replaced by hash + downloader + added-time receipts.
Brush-flow sources are excluded in this first release.
