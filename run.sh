#!/bin/sh
# Launch LibreHome on Linux (macOS too). Needs only Python 3.10+.
cd "$(dirname "$0")" && PYTHONPATH=src exec python3 -m librehome serve "$@"
