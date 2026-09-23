"""Starting background work and following it to the end."""

from __future__ import annotations

from typing import Any

from arq.jobs import Job, JobStatus
from fastapi import APIRouter, status

from dealsignal.core.deps import JobQueueDep
from dealsignal.core.errors import ConflictError
from dealsignal.schemas.jobs import (
    EnrichRequest,
    JobStarted,
    JobState,
    JobStatusName,
    RegistryRequest,
    SeedRequest,
    WebsiteReadRequest,
)

router = APIRouter(prefix="/jobs", tags=["jobs"])

INTERRUPTED = "retries exceeded"
INTERRUPTED_MESSAGE = (
    "The job was interrupted before it finished, usually because the worker restarted. "
    "Everything it had already saved was kept, and running it again continues where it "
    "left off."
)

STATUS_NAMES: dict[JobStatus, JobStatusName] = {
    JobStatus.deferred: "queued",
    JobStatus.queued: "queued",
    JobStatus.in_progress: "in_progress",
    JobStatus.complete: "complete",
    JobStatus.not_found: "not_found",
}


async def _enqueue(queue: JobQueueDep, kind: str, **params: Any) -> JobStarted:
    job = await queue.enqueue_job(kind, **params)
    if job is None:
        # arq returns None when an identical job id is already queued.
        raise ConflictError("That job is already queued.")
    return JobStarted(id=job.job_id, kind=kind)


@router.post("/seed", response_model=JobStarted, status_code=status.HTTP_202_ACCEPTED)
async def start_seed(payload: SeedRequest, queue: JobQueueDep) -> JobStarted:
    """Load companies for a region and industry from open data."""
    return await _enqueue(
        queue, "seed_region", region=payload.region, industry=payload.industry, limit=payload.limit
    )


@router.post("/registry", response_model=JobStarted, status_code=status.HTTP_202_ACCEPTED)
async def start_registry(payload: RegistryRequest, queue: JobQueueDep) -> JobStarted:
    """Match companies to their national company register."""
    return await _enqueue(
        queue, "lookup_registry", country=str(payload.country), limit=payload.limit
    )


@router.post("/domain-age", response_model=JobStarted, status_code=status.HTTP_202_ACCEPTED)
async def start_domain_age(payload: EnrichRequest, queue: JobQueueDep) -> JobStarted:
    """Look up when each company's website domain was registered."""
    return await _enqueue(queue, "check_domain_age", limit=payload.limit)


@router.post("/websites", response_model=JobStarted, status_code=status.HTTP_202_ACCEPTED)
async def start_websites(payload: WebsiteReadRequest, queue: JobQueueDep) -> JobStarted:
    """Read company websites with Claude."""
    return await _enqueue(queue, "read_websites", limit=payload.limit)


@router.get("/{job_id}", response_model=JobState)
async def get_job(job_id: str, queue: JobQueueDep) -> JobState:
    """Poll a job. A job that raised is reported as failed, with its error."""
    job = Job(job_id, queue)
    job_status = await job.status()
    state = JobState(id=job_id, status=STATUS_NAMES[job_status])

    if job_status is not JobStatus.complete:
        return state

    info = await job.result_info()
    if info is None:
        return state
    if not info.success:
        error = str(info.result)
        return state.model_copy(
            update={
                "kind": info.function,
                "status": "failed",
                "error": INTERRUPTED_MESSAGE if INTERRUPTED in error else error,
            }
        )
    return state.model_copy(update={"kind": info.function, "result": info.result})
