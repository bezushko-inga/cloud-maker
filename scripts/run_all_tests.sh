#!/bin/bash
set -o pipefail

cd "$(dirname "$0")/.." || exit 1

python3 -m pytest tests/ -v -ra

result=$?

if [ "$result" -eq 0 ]; then
    echo "ALL TESTS PASSED"
else
    echo "TESTS FAILED"
fi

exit "$result"