#!/usr/bin/env bash
# 全選挙回について 抽出 → 検証 → JSON生成 → pytest を通しで回す。
#
# 共通コード（common.py や各 t_*.py）はすべての選挙回で共有しているため、
# ある回のために手を入れたら必ず全回を回し直すこと。
set -uo pipefail

cd "$(dirname "$0")"
export PYTHONPATH=src

ELECTIONS=("r08-02-08" "r06-10-27")
STATUS=0

for id in "${ELECTIONS[@]}"; do
    echo "=============================================================="
    echo " $id"
    echo "=============================================================="
    for step in "extract.run_all" "verify.run_verify" "build_json"; do
        if python3 -m "$step" "$id" > "/tmp/regression-$id-${step//./-}.log" 2>&1; then
            echo "  [OK]   $step"
        else
            echo "  [FAIL] $step  — /tmp/regression-$id-${step//./-}.log"
            tail -20 "/tmp/regression-$id-${step//./-}.log" | sed 's/^/         /'
            STATUS=1
        fi
    done
done

echo "=============================================================="
if python3 -m pytest -q tests > /tmp/regression-pytest.log 2>&1; then
    echo "  [OK]   pytest"
    tail -3 /tmp/regression-pytest.log | sed 's/^/         /'
else
    echo "  [FAIL] pytest"
    tail -30 /tmp/regression-pytest.log | sed 's/^/         /'
    STATUS=1
fi

echo
[ $STATUS -eq 0 ] && echo "リグレッション: 全通過" || echo "リグレッション: 失敗あり"
exit $STATUS
