# Private OpenCC dependency

`opencc/` contains the unmodified Python implementation, configuration and
dictionary files from `opencc-python-reimplemented==0.1.7`, plus its Apache-2.0
LICENSE. Upstream NOTICE is retained. Source: https://github.com/yichen0831/opencc-python

Wheel SHA-256: `41b3b92943c7bed291f448e9c7fad4b577c8c2eae30fcfe5a74edf8818493aa6`.
Reproduce with `scripts/vendor-subtitle-opencc.py`. No pip installation, global
module aliases, sys.path changes or runtime network download are used.
