"""Hospital environment — agent tools."""
import requests
from langchain_core.tools import tool

from ._runtime import api_url, call


@tool
def list_doctors(available_at: str) -> list | dict:
    """List doctors. If available_at is an ISO time (e.g. '2026-11-05T09:00'),
    only returns doctors with no appointment at that time. Returns
    [{id, name, department_id}]."""
    params = {"available_at": available_at} if available_at else {}
    return call(requests.get(f"{api_url('hospital')}/doctors", params=params))


@tool
def schedule_appointment(patient_id: int, doctor_id: int, time: str) -> dict:
    """Schedule an appointment. time is ISO like '2026-11-06T14:00'.
    Returns {id, patient_id, doctor_id, time, status}."""
    return call(requests.post(
        f"{api_url('hospital')}/appointments",
        json={"patient_id": patient_id, "doctor_id": doctor_id, "time": time},
    ))


@tool
def cancel_appointment(appointment_id: int) -> dict:
    """Cancel a scheduled appointment by id."""
    return call(requests.post(
        f"{api_url('hospital')}/appointments/{appointment_id}/cancel"
    ))


TOOLS = [list_doctors, schedule_appointment, cancel_appointment]