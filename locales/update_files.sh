#!/bin/bash
set -euo pipefail

find locales -type f -name "*.po" -print0 | xargs -0 -I {} sh -c '
    po_file="{}"
    mo_file="${po_file%.po}.mo"
    msgfmt -o "$mo_file" "$po_file"
'