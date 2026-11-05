# test_grader.py
from grade import grade

task = {
    "mode": "delta",
    "expected_state": {
        "appointments": [
            {"patient_id": 3, "time": "2026-11-05T09:00", "status": "scheduled"},
        ],
    },
}

before = {"appointments": [
    {"id": 1, "patient_id": 1, "doctor_id": 1, "time": "2026-11-05T09:00", "status": "scheduled"},
    {"id": 2, "patient_id": 2, "doctor_id": 3, "time": "2026-11-05T10:00", "status": "scheduled"},
]}

after_ok = {"appointments": before["appointments"] + [
    {"id": 3, "patient_id": 3, "doctor_id": 2, "time": "2026-11-05T09:00", "status": "scheduled"},
]}
ok, msg = grade(task, before, after_ok)
assert ok, f"expected pass, got {msg}"
print("[PASS] delta: one new row → pass")

after_dup = {"appointments": before["appointments"] + [
    {"id": 3, "patient_id": 3, "doctor_id": 2, "time": "2026-11-05T09:00", "status": "scheduled"},
    {"id": 4, "patient_id": 3, "doctor_id": 2, "time": "2026-11-05T09:00", "status": "scheduled"},
]}
ok, msg = grade(task, before, after_dup)
assert not ok, f"expected fail on duplicate, got {msg}"
print(f"[PASS] delta: duplicate → fail ({msg})")

ok, msg = grade(task, before, before)
assert not ok, f"expected fail on no change, got {msg}"
print(f"[PASS] delta: no change → fail ({msg})")