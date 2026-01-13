"""Kubernetes-related models for job management."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class JobStatus(str, Enum):
    """Status of a Kubernetes Job."""

    PENDING = "pending"  # Job created, pod not yet scheduled
    RUNNING = "running"  # Pod is running
    SUCCEEDED = "succeeded"  # Job completed successfully
    FAILED = "failed"  # Job failed


class JobInfo(BaseModel):
    """Information about a Kubernetes Job.

    Attributes:
        name: Name of the job
        namespace: Kubernetes namespace
        status: Current job status
        start_time: When the job started running
        completion_time: When the job completed (success or failure)
        pod_name: Name of the pod running the job
        exit_code: Exit code of the main container (if completed)
        error_message: Error message if job failed
    """

    name: str
    namespace: str
    status: JobStatus
    start_time: datetime | None = Field(default=None, alias="startTime")
    completion_time: datetime | None = Field(default=None, alias="completionTime")
    pod_name: str | None = Field(default=None, alias="podName")
    exit_code: int | None = Field(default=None, alias="exitCode")
    error_message: str | None = Field(default=None, alias="errorMessage")

    class Config:
        populate_by_name = True
