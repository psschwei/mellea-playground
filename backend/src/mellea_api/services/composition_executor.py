"""CompositionExecutor for executing composition workflows on Kubernetes."""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from mellea_api.core.config import Settings, get_settings
from mellea_api.core.store import JsonStore
from mellea_api.models.assets import CompositionAsset
from mellea_api.models.common import RunExecutionStatus
from mellea_api.models.composition_run import (
    VALID_COMPOSITION_RUN_TRANSITIONS,
    CompositionRun,
    NodeExecutionStatus,
)
from mellea_api.services.assets import AssetService, get_asset_service
from mellea_api.services.code_generator import (
    CodeGenerator,
    GeneratedCode,
    get_code_generator,
    to_variable_name,
)
from mellea_api.services.credentials import CredentialService, get_credential_service
from mellea_api.services.environment import EnvironmentService, get_environment_service
from mellea_api.services.k8s_jobs import K8sJobService, get_k8s_job_service
from mellea_api.services.log import LogService, get_log_service

logger = logging.getLogger(__name__)


# =============================================================================
# Exceptions
# =============================================================================


class CompositionNotFoundError(Exception):
    """Raised when a composition is not found."""

    pass


class CompositionRunNotFoundError(Exception):
    """Raised when a composition run is not found."""

    pass


class CompositionValidationError(Exception):
    """Raised when composition validation fails."""

    def __init__(self, message: str, errors: list[str] | None = None) -> None:
        super().__init__(message)
        self.errors = errors or []


class InvalidCompositionRunStateTransitionError(Exception):
    """Raised when an invalid state transition is attempted."""

    pass


class EnvironmentNotReadyError(Exception):
    """Raised when trying to run in an environment that's not ready."""

    pass


class CredentialValidationError(Exception):
    """Raised when credential validation fails before run submission."""

    pass


class CannotResumeRunError(Exception):
    """Raised when a run cannot be resumed (not failed, no failed nodes, etc.)."""

    pass


# =============================================================================
# Validation Result
# =============================================================================


@dataclass
class ValidationResult:
    """Result of composition validation."""

    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    program_ids: list[str] = field(default_factory=list)
    model_ids: list[str] = field(default_factory=list)


# =============================================================================
# CompositionRunService
# =============================================================================


class CompositionRunService:
    """Service for managing composition run lifecycle.

    Manages the lifecycle of composition runs from creation (queuing) through
    completion, enforcing valid state transitions and tracking execution state.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        """Initialize the CompositionRunService.

        Args:
            settings: Application settings (uses default if not provided)
        """
        self.settings = settings or get_settings()
        self._run_store: JsonStore[CompositionRun] | None = None

    @property
    def run_store(self) -> JsonStore[CompositionRun]:
        """Get the composition run store, initializing if needed."""
        if self._run_store is None:
            file_path = self.settings.data_dir / "metadata" / "composition_runs.json"
            self._run_store = JsonStore[CompositionRun](
                file_path=file_path,
                collection_key="compositionRuns",
                model_class=CompositionRun,
            )
        return self._run_store

    def _validate_transition(
        self, current: RunExecutionStatus, target: RunExecutionStatus
    ) -> bool:
        """Validate if a state transition is allowed."""
        if current == target:
            return True
        allowed = VALID_COMPOSITION_RUN_TRANSITIONS.get(current, set())
        return target in allowed

    def _assert_transition(
        self, run_id: str, current: RunExecutionStatus, target: RunExecutionStatus
    ) -> None:
        """Assert that a state transition is valid, raising if not."""
        if not self._validate_transition(current, target):
            raise InvalidCompositionRunStateTransitionError(
                f"Invalid transition for composition run {run_id}: "
                f"{current.value} -> {target.value}"
            )

    def create_run(
        self,
        owner_id: str,
        environment_id: str,
        composition_id: str,
        inputs: dict[str, Any] | None = None,
        credential_ids: list[str] | None = None,
    ) -> CompositionRun:
        """Create a new composition run in QUEUED status.

        Args:
            owner_id: ID of the user creating the run
            environment_id: ID of the environment to run in
            composition_id: ID of the composition being executed
            inputs: Input values for the composition
            credential_ids: List of credential IDs to inject as secrets

        Returns:
            The created CompositionRun in QUEUED status
        """
        run = CompositionRun(
            ownerId=owner_id,
            environmentId=environment_id,
            compositionId=composition_id,
            status=RunExecutionStatus.QUEUED,
            inputs=inputs or {},
            credentialIds=credential_ids or [],
        )
        created = self.run_store.create(run)
        logger.info(
            f"Created composition run {created.id} for composition {composition_id} "
            f"in environment {environment_id}"
        )
        return created

    def get_run(self, run_id: str) -> CompositionRun | None:
        """Get a composition run by ID."""
        return self.run_store.get_by_id(run_id)

    def list_runs(
        self,
        owner_id: str | None = None,
        environment_id: str | None = None,
        composition_id: str | None = None,
        status: RunExecutionStatus | None = None,
    ) -> list[CompositionRun]:
        """List composition runs with optional filtering."""
        runs = self.run_store.list_all()

        if owner_id:
            runs = [r for r in runs if r.owner_id == owner_id]
        if environment_id:
            runs = [r for r in runs if r.environment_id == environment_id]
        if composition_id:
            runs = [r for r in runs if r.composition_id == composition_id]
        if status:
            runs = [r for r in runs if r.status == status]

        return runs

    def update_run(self, run: CompositionRun) -> CompositionRun:
        """Update a composition run.

        Args:
            run: The updated run

        Returns:
            Updated CompositionRun

        Raises:
            CompositionRunNotFoundError: If run doesn't exist
        """
        updated = self.run_store.update(run.id, run)
        if updated is None:
            raise CompositionRunNotFoundError(f"Composition run not found: {run.id}")
        return updated

    def start_run(
        self, run_id: str, job_name: str, execution_order: list[str], generated_code: str
    ) -> CompositionRun:
        """Start a composition run (transition QUEUED -> STARTING).

        Args:
            run_id: Run's unique identifier
            job_name: Name of the K8s job created for this run
            execution_order: List of node IDs in execution order
            generated_code: The generated Python code

        Returns:
            Updated CompositionRun in STARTING status
        """
        run = self.run_store.get_by_id(run_id)
        if run is None:
            raise CompositionRunNotFoundError(f"Composition run not found: {run_id}")

        self._assert_transition(run_id, run.status, RunExecutionStatus.STARTING)

        run.status = RunExecutionStatus.STARTING
        run.job_name = job_name
        run.generated_code = generated_code
        run.initialize_node_states(execution_order)

        updated = self.run_store.update(run_id, run)
        if updated is None:
            raise CompositionRunNotFoundError(f"Composition run not found: {run_id}")

        logger.info(f"Composition run {run_id} transitioned to STARTING")
        return updated

    def mark_running(self, run_id: str, output: str | None = None) -> CompositionRun:
        """Mark a composition run as running."""
        run = self.run_store.get_by_id(run_id)
        if run is None:
            raise CompositionRunNotFoundError(f"Composition run not found: {run_id}")

        self._assert_transition(run_id, run.status, RunExecutionStatus.RUNNING)

        run.status = RunExecutionStatus.RUNNING
        run.started_at = datetime.utcnow()
        if output:
            run.output = output

        updated = self.run_store.update(run_id, run)
        if updated is None:
            raise CompositionRunNotFoundError(f"Composition run not found: {run_id}")

        logger.info(f"Composition run {run_id} transitioned to RUNNING")
        return updated

    def mark_succeeded(
        self,
        run_id: str,
        exit_code: int = 0,
        output: str | None = None,
        outputs: dict[str, Any] | None = None,
    ) -> CompositionRun:
        """Mark a composition run as succeeded."""
        run = self.run_store.get_by_id(run_id)
        if run is None:
            raise CompositionRunNotFoundError(f"Composition run not found: {run_id}")

        self._assert_transition(run_id, run.status, RunExecutionStatus.SUCCEEDED)

        run.status = RunExecutionStatus.SUCCEEDED
        run.exit_code = exit_code
        run.completed_at = datetime.utcnow()
        if output:
            run.output = output
        if outputs:
            run.outputs = outputs

        updated = self.run_store.update(run_id, run)
        if updated is None:
            raise CompositionRunNotFoundError(f"Composition run not found: {run_id}")

        logger.info(f"Composition run {run_id} transitioned to SUCCEEDED")
        return updated

    def mark_failed(
        self,
        run_id: str,
        exit_code: int | None = None,
        error: str | None = None,
        output: str | None = None,
    ) -> CompositionRun:
        """Mark a composition run as failed."""
        run = self.run_store.get_by_id(run_id)
        if run is None:
            raise CompositionRunNotFoundError(f"Composition run not found: {run_id}")

        self._assert_transition(run_id, run.status, RunExecutionStatus.FAILED)

        run.status = RunExecutionStatus.FAILED
        run.exit_code = exit_code
        run.completed_at = datetime.utcnow()
        run.error_message = error
        if output:
            run.output = output

        updated = self.run_store.update(run_id, run)
        if updated is None:
            raise CompositionRunNotFoundError(f"Composition run not found: {run_id}")

        logger.info(f"Composition run {run_id} transitioned to FAILED: {error}")
        return updated

    def cancel_run(self, run_id: str) -> CompositionRun:
        """Cancel a composition run."""
        run = self.run_store.get_by_id(run_id)
        if run is None:
            raise CompositionRunNotFoundError(f"Composition run not found: {run_id}")

        self._assert_transition(run_id, run.status, RunExecutionStatus.CANCELLED)

        run.status = RunExecutionStatus.CANCELLED
        run.completed_at = datetime.utcnow()

        updated = self.run_store.update(run_id, run)
        if updated is None:
            raise CompositionRunNotFoundError(f"Composition run not found: {run_id}")

        logger.info(f"Composition run {run_id} cancelled")
        return updated

    def update_node_state(
        self,
        run_id: str,
        node_id: str,
        status: NodeExecutionStatus,
        output: Any = None,
        error: str | None = None,
    ) -> CompositionRun:
        """Update the execution state for a specific node.

        Args:
            run_id: Run's unique identifier
            node_id: Node's unique identifier
            status: New status for the node
            output: Optional output from the node
            error: Optional error message if failed

        Returns:
            Updated CompositionRun
        """
        run = self.run_store.get_by_id(run_id)
        if run is None:
            raise CompositionRunNotFoundError(f"Composition run not found: {run_id}")

        run.update_node_state(node_id, status, output, error)

        updated = self.run_store.update(run_id, run)
        if updated is None:
            raise CompositionRunNotFoundError(f"Composition run not found: {run_id}")

        logger.debug(f"Node {node_id} in run {run_id} transitioned to {status.value}")
        return updated

    def append_node_log(
        self,
        run_id: str,
        node_id: str,
        message: str,
    ) -> CompositionRun:
        """Append a log message to a specific node's execution state.

        Args:
            run_id: Run's unique identifier
            node_id: Node's unique identifier
            message: Log message to append

        Returns:
            Updated CompositionRun
        """
        run = self.run_store.get_by_id(run_id)
        if run is None:
            raise CompositionRunNotFoundError(f"Composition run not found: {run_id}")

        # Get or create node state
        if node_id not in run.node_states:
            raise CompositionRunNotFoundError(
                f"Node {node_id} not found in composition run {run_id}"
            )

        run.node_states[node_id].append_log(message)

        updated = self.run_store.update(run_id, run)
        if updated is None:
            raise CompositionRunNotFoundError(f"Composition run not found: {run_id}")

        logger.debug(f"Appended log to node {node_id} in run {run_id}: {message[:50]}...")
        return updated

    def delete_run(self, run_id: str) -> bool:
        """Delete a composition run by ID.

        Only runs in terminal states can be deleted.
        """
        run = self.run_store.get_by_id(run_id)
        if run is None:
            raise CompositionRunNotFoundError(f"Composition run not found: {run_id}")

        if not run.is_terminal():
            raise InvalidCompositionRunStateTransitionError(
                f"Cannot delete composition run {run_id} in status {run.status.value}. "
                "Only runs in terminal states can be deleted."
            )

        deleted = self.run_store.delete(run_id)
        if deleted:
            logger.info(f"Deleted composition run {run_id}")
        return deleted


# =============================================================================
# CompositionExecutor
# =============================================================================


class CompositionExecutor:
    """Executor for validating, generating code, and running composition workflows.

    This service orchestrates composition execution by:
    - Validating compositions (checking referenced assets)
    - Generating executable Python code from the graph
    - Submitting runs as Kubernetes Jobs
    - Tracking job status and updating run state

    Example:
        ```python
        executor = get_composition_executor()

        # Validate a composition
        result = executor.validate_composition(composition_id)
        if not result.valid:
            print(f"Validation errors: {result.errors}")

        # Execute a composition
        run = await executor.execute_composition(
            owner_id="user-123",
            composition_id="comp-456",
            environment_id="env-789",
            inputs={"prompt": "Hello, world!"},
        )

        # Check status periodically
        run = executor.sync_run_status(run.id)
        ```
    """

    def __init__(
        self,
        run_service: CompositionRunService | None = None,
        asset_service: AssetService | None = None,
        k8s_service: K8sJobService | None = None,
        environment_service: EnvironmentService | None = None,
        credential_service: CredentialService | None = None,
        log_service: LogService | None = None,
        code_generator: CodeGenerator | None = None,
    ) -> None:
        """Initialize the CompositionExecutor.

        Args:
            run_service: CompositionRunService instance
            asset_service: AssetService instance
            k8s_service: K8sJobService instance
            environment_service: EnvironmentService instance
            credential_service: CredentialService instance
            log_service: LogService instance
            code_generator: CodeGenerator instance
        """
        self._run_service = run_service
        self._asset_service = asset_service
        self._k8s_service = k8s_service
        self._environment_service = environment_service
        self._credential_service = credential_service
        self._log_service = log_service
        self._code_generator = code_generator

    @property
    def run_service(self) -> CompositionRunService:
        """Get the CompositionRunService."""
        if self._run_service is None:
            self._run_service = get_composition_run_service()
        return self._run_service

    @property
    def asset_service(self) -> AssetService:
        """Get the AssetService."""
        if self._asset_service is None:
            self._asset_service = get_asset_service()
        return self._asset_service

    @property
    def k8s_service(self) -> K8sJobService:
        """Get the K8sJobService."""
        if self._k8s_service is None:
            self._k8s_service = get_k8s_job_service()
        return self._k8s_service

    @property
    def environment_service(self) -> EnvironmentService:
        """Get the EnvironmentService."""
        if self._environment_service is None:
            self._environment_service = get_environment_service()
        return self._environment_service

    @property
    def credential_service(self) -> CredentialService:
        """Get the CredentialService."""
        if self._credential_service is None:
            self._credential_service = get_credential_service()
        return self._credential_service

    @property
    def log_service(self) -> LogService:
        """Get the LogService."""
        if self._log_service is None:
            self._log_service = get_log_service()
        return self._log_service

    @property
    def code_generator(self) -> CodeGenerator:
        """Get the CodeGenerator."""
        if self._code_generator is None:
            self._code_generator = get_code_generator()
        return self._code_generator

    def _get_composition(self, composition_id: str) -> CompositionAsset:
        """Get a composition by ID.

        Args:
            composition_id: Composition ID

        Returns:
            CompositionAsset

        Raises:
            CompositionNotFoundError: If composition doesn't exist
        """
        composition = self.asset_service.get_composition(composition_id)
        if composition is None:
            raise CompositionNotFoundError(f"Composition not found: {composition_id}")
        return composition

    def validate_composition(self, composition_id: str) -> ValidationResult:
        """Validate a composition for execution.

        Checks that:
        - All referenced programs exist
        - All referenced models exist
        - The graph has no cycles
        - Required node parameters are set

        Args:
            composition_id: ID of the composition to validate

        Returns:
            ValidationResult with errors and warnings
        """
        errors: list[str] = []
        warnings: list[str] = []
        program_ids: list[str] = []
        model_ids: list[str] = []

        try:
            composition = self._get_composition(composition_id)
        except CompositionNotFoundError as e:
            return ValidationResult(valid=False, errors=[str(e)])

        # Check referenced programs
        for program_id in composition.program_refs:
            program = self.asset_service.get_program(program_id)
            if program is None:
                errors.append(f"Referenced program not found: {program_id}")
            else:
                program_ids.append(program_id)

        # Check referenced models
        for model_id in composition.model_refs:
            model = self.asset_service.get_model(model_id)
            if model is None:
                errors.append(f"Referenced model not found: {model_id}")
            else:
                model_ids.append(model_id)

        # Check graph structure
        nodes = composition.graph.nodes
        edges = composition.graph.edges

        if not nodes:
            errors.append("Composition has no nodes")
        else:
            # Check for cycles using topological sort
            order, has_cycle = self.code_generator.get_execution_order(nodes, edges)
            if has_cycle:
                errors.append(
                    "Composition graph contains a cycle - execution order cannot be determined"
                )

            # Check node references
            for node in nodes:
                data = node.get("data", {})
                category = data.get("category", "")

                if category == "program":
                    program_id = data.get("programId")
                    if program_id and program_id not in composition.program_refs:
                        warnings.append(
                            f"Node {node['id']} references program {program_id} "
                            "not in composition's programRefs"
                        )

                elif category == "model":
                    model_id = data.get("modelId")
                    if model_id and model_id not in composition.model_refs:
                        warnings.append(
                            f"Node {node['id']} references model {model_id} "
                            "not in composition's modelRefs"
                        )

        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            program_ids=program_ids,
            model_ids=model_ids,
        )

    def generate_code(self, composition_id: str) -> GeneratedCode:
        """Generate executable Python code from a composition.

        Args:
            composition_id: ID of the composition

        Returns:
            GeneratedCode with Python source and metadata

        Raises:
            CompositionNotFoundError: If composition doesn't exist
        """
        composition = self._get_composition(composition_id)
        nodes = composition.graph.nodes
        edges = composition.graph.edges

        return self.code_generator.generate(nodes, edges)

    def submit_run(
        self,
        owner_id: str,
        composition_id: str,
        environment_id: str,
        inputs: dict[str, Any] | None = None,
        credential_ids: list[str] | None = None,
        validate: bool = True,
    ) -> CompositionRun:
        """Submit a composition for execution.

        Creates a CompositionRun, validates the composition, generates code,
        and submits a K8s job for execution.

        Args:
            owner_id: ID of the user submitting the run
            composition_id: ID of the composition to run
            environment_id: ID of the environment to run in
            inputs: Input values for the composition
            credential_ids: List of credential IDs to inject
            validate: Whether to validate before submission (default True)

        Returns:
            Created CompositionRun

        Raises:
            CompositionNotFoundError: If composition doesn't exist
            CompositionValidationError: If validation fails
            EnvironmentNotReadyError: If environment is not ready
            CredentialValidationError: If credential validation fails
        """
        # Validate composition if requested
        if validate:
            validation = self.validate_composition(composition_id)
            if not validation.valid:
                raise CompositionValidationError(
                    f"Composition validation failed: {', '.join(validation.errors)}",
                    errors=validation.errors,
                )

        # Generate code (validates composition exists)
        generated = self.generate_code(composition_id)

        # Get the environment
        env = self.environment_service.get_environment(environment_id)
        if env is None:
            raise EnvironmentNotReadyError(f"Environment not found: {environment_id}")
        if not env.image_tag:
            raise EnvironmentNotReadyError(
                f"Environment {environment_id} has no image tag"
            )

        # Validate credentials
        cred_ids = credential_ids or []
        for cred_id in cred_ids:
            credential = self.credential_service.get_credential(cred_id)
            if credential is None:
                raise CredentialValidationError(f"Credential not found: {cred_id}")
            if credential.is_expired:
                raise CredentialValidationError(f"Credential has expired: {cred_id}")

        # Create the run record
        run = self.run_service.create_run(
            owner_id=owner_id,
            environment_id=environment_id,
            composition_id=composition_id,
            inputs=inputs,
            credential_ids=cred_ids,
        )

        # Generate job name and transition to STARTING
        job_name = f"mellea-comp-{run.id[:8].lower()}"
        run = self.run_service.start_run(
            run.id,
            job_name=job_name,
            execution_order=generated.execution_order,
            generated_code=generated.code,
        )

        # Resolve credential IDs to K8s secret names
        secret_names: list[str] = []
        for cred_id in cred_ids:
            secret_name = self.credential_service.get_k8s_secret_name(cred_id)
            if secret_name:
                secret_names.append(secret_name)
                logger.debug("Resolved credential %s to secret %s", cred_id, secret_name)

        # Create the K8s job
        try:
            self.k8s_service.create_run_job(
                environment_id=run.environment_id,
                image_tag=env.image_tag,
                resource_limits=env.resource_limits,
                entrypoint="composition_runner.py",  # Generated code runner
                secret_names=secret_names,
            )
        except RuntimeError as e:
            # Mark run as failed if job creation fails
            logger.error("Failed to create K8s job for composition run %s: %s", run.id, e)
            return self.run_service.mark_failed(
                run.id, error=f"Failed to create K8s job: {e}"
            )

        logger.info("Submitted composition run %s as K8s job %s", run.id, job_name)
        return run

    def sync_run_status(self, run_id: str) -> CompositionRun:
        """Sync a composition run's status with its K8s job status.

        Args:
            run_id: ID of the run to sync

        Returns:
            Updated CompositionRun with current status

        Raises:
            CompositionRunNotFoundError: If run doesn't exist
        """
        run = self.run_service.get_run(run_id)
        if run is None:
            raise CompositionRunNotFoundError(f"Composition run not found: {run_id}")

        # Only sync runs that have been submitted to K8s
        if run.job_name is None:
            logger.debug("Composition run %s has no job name, skipping sync", run_id)
            return run

        # Skip terminal runs
        if run.is_terminal():
            logger.debug("Composition run %s is terminal, skipping sync", run_id)
            return run

        # Get job status from K8s
        try:
            job_info = self.k8s_service.get_job_status(run.job_name)
        except RuntimeError as e:
            logger.error(
                "Failed to get job status for composition run %s: %s", run_id, e
            )
            return self.run_service.mark_failed(
                run_id, error=f"Failed to get job status: {e}"
            )

        # Update run based on job status
        from mellea_api.services.run_executor import JOB_STATUS_TO_RUN_STATUS

        current_status = run.status
        target_status = JOB_STATUS_TO_RUN_STATUS.get(job_info.status)

        if target_status is None:
            logger.warning(
                "Unknown job status %s for composition run %s", job_info.status, run.id
            )
            return run

        # Fetch pod logs if available
        output = None
        if run.job_name:
            output = self.k8s_service.get_pod_logs(run.job_name)

        # No status change needed
        if current_status == target_status:
            if output and output != run.output:
                run.output = output
                run = self.run_service.update_run(run)
                self.log_service.publish_logs_sync(run.id, output)
            return run

        # Update based on target status
        is_terminal = False
        if target_status == RunExecutionStatus.RUNNING:
            run = self.run_service.mark_running(run.id, output=output)
        elif target_status == RunExecutionStatus.SUCCEEDED:
            run = self.run_service.mark_succeeded(run.id, exit_code=job_info.exit_code or 0, output=output)
            is_terminal = True
        elif target_status == RunExecutionStatus.FAILED:
            run = self.run_service.mark_failed(
                run.id,
                exit_code=job_info.exit_code,
                error=job_info.error_message,
                output=output,
            )
            is_terminal = True

        # Publish logs
        if output:
            self.log_service.publish_logs_sync(run.id, output, is_complete=is_terminal)

        # Clean up K8s job after completion
        if run.is_terminal() and run.job_name:
            try:
                self.k8s_service.delete_job(run.job_name)
                logger.info(
                    "Cleaned up completed K8s job %s for composition run %s",
                    run.job_name,
                    run.id,
                )
            except Exception as e:
                logger.warning("Failed to clean up job %s: %s", run.job_name, e)

        return run

    def cancel_run(self, run_id: str, force: bool = False) -> CompositionRun:
        """Cancel a composition run and its K8s job.

        Args:
            run_id: ID of the run to cancel
            force: If True, immediately terminates without grace period

        Returns:
            Updated CompositionRun in CANCELLED status

        Raises:
            CompositionRunNotFoundError: If run doesn't exist
        """
        run = self.run_service.get_run(run_id)
        if run is None:
            raise CompositionRunNotFoundError(f"Composition run not found: {run_id}")

        # Cancel K8s job if it exists
        if run.job_name is not None:
            try:
                self.k8s_service.cancel_job(run.job_name, force=force)
                if force:
                    logger.info(
                        "Force cancelled K8s job %s for composition run %s",
                        run.job_name,
                        run_id,
                    )
                else:
                    logger.info(
                        "Gracefully cancelled K8s job %s for composition run %s",
                        run.job_name,
                        run_id,
                    )
            except RuntimeError as e:
                logger.warning(
                    "Failed to cancel K8s job %s for composition run %s: %s",
                    run.job_name,
                    run_id,
                    e,
                )

        # Cancel the run
        return self.run_service.cancel_run(run_id)

    def resume_run(
        self,
        run_id: str,
        from_node_id: str | None = None,
    ) -> CompositionRun:
        """Resume a failed composition run from a specific node.

        Creates a new run that reuses the outputs from succeeded nodes in the
        original run and re-executes starting from the specified node (or the
        first failed node if not specified).

        Args:
            run_id: ID of the failed run to resume
            from_node_id: Node ID to resume from. If None, resumes from the
                first failed node in execution order.

        Returns:
            New CompositionRun that continues from the specified node

        Raises:
            CompositionRunNotFoundError: If the original run doesn't exist
            CannotResumeRunError: If the run cannot be resumed (not failed,
                composition changed, etc.)
        """
        # Get the original run
        original_run = self.run_service.get_run(run_id)
        if original_run is None:
            raise CompositionRunNotFoundError(f"Composition run not found: {run_id}")

        # Validate the run is in a resumable state
        if original_run.status != RunExecutionStatus.FAILED:
            raise CannotResumeRunError(
                f"Cannot resume run {run_id}: run is in {original_run.status.value} state, "
                "only FAILED runs can be resumed"
            )

        if not original_run.has_failed_nodes():
            raise CannotResumeRunError(
                f"Cannot resume run {run_id}: no failed nodes found"
            )

        # Determine the node to resume from
        if from_node_id is None:
            # Find the first failed node in execution order
            for node_id in original_run.execution_order:
                state = original_run.get_node_state(node_id)
                if state and state.status == NodeExecutionStatus.FAILED:
                    from_node_id = node_id
                    break

        if from_node_id is None:
            raise CannotResumeRunError(
                f"Cannot resume run {run_id}: could not determine resume point"
            )

        # Validate the from_node_id exists in the execution order
        if from_node_id not in original_run.execution_order:
            raise CannotResumeRunError(
                f"Cannot resume run {run_id}: node {from_node_id} not found in execution order"
            )

        # Get the composition (validates it still exists)
        try:
            composition = self._get_composition(original_run.composition_id)
        except CompositionNotFoundError as e:
            raise CannotResumeRunError(
                f"Cannot resume run {run_id}: composition no longer exists"
            ) from e

        # Get the environment
        env = self.environment_service.get_environment(original_run.environment_id)
        if env is None:
            raise CannotResumeRunError(
                f"Cannot resume run {run_id}: environment no longer exists"
            )
        if not env.image_tag:
            raise CannotResumeRunError(
                f"Cannot resume run {run_id}: environment has no image tag"
            )

        # Build cached outputs from succeeded nodes before the resume point
        cached_outputs: dict[str, Any] = {}
        resume_index = original_run.execution_order.index(from_node_id)

        for i, node_id in enumerate(original_run.execution_order):
            if i >= resume_index:
                break
            state = original_run.get_node_state(node_id)
            if state and state.status == NodeExecutionStatus.SUCCEEDED:
                cached_outputs[node_id] = state.output

        # Generate code with cached outputs
        nodes = composition.graph.nodes
        edges = composition.graph.edges
        generated = self.code_generator.generate(nodes, edges)

        # Modify the generated code to include cached outputs
        modified_code = self._inject_cached_outputs(
            generated.code, cached_outputs, from_node_id
        )

        # Validate credentials if any
        cred_ids = original_run.credential_ids or []
        for cred_id in cred_ids:
            credential = self.credential_service.get_credential(cred_id)
            if credential is None:
                raise CannotResumeRunError(
                    f"Cannot resume run {run_id}: credential {cred_id} no longer exists"
                )
            if credential.is_expired:
                raise CannotResumeRunError(
                    f"Cannot resume run {run_id}: credential {cred_id} has expired"
                )

        # Create a new run
        new_run = self.run_service.create_run(
            owner_id=original_run.owner_id,
            environment_id=original_run.environment_id,
            composition_id=original_run.composition_id,
            inputs=original_run.inputs,
            credential_ids=cred_ids,
        )

        # Generate job name and transition to STARTING
        job_name = f"mellea-comp-{new_run.id[:8].lower()}"
        new_run = self.run_service.start_run(
            new_run.id,
            job_name=job_name,
            execution_order=generated.execution_order,
            generated_code=modified_code,
        )

        # Mark nodes before resume point as SKIPPED with their cached outputs
        for node_id, output in cached_outputs.items():
            self.run_service.update_node_state(
                new_run.id,
                node_id,
                NodeExecutionStatus.SKIPPED,
                output=output,
            )
            # Add a log entry explaining why this node was skipped
            self.run_service.append_node_log(
                new_run.id,
                node_id,
                f"Skipped: using cached output from previous run {run_id}",
            )

        # Resolve credential IDs to K8s secret names
        secret_names: list[str] = []
        for cred_id in cred_ids:
            secret_name = self.credential_service.get_k8s_secret_name(cred_id)
            if secret_name:
                secret_names.append(secret_name)

        # Create the K8s job
        try:
            self.k8s_service.create_run_job(
                environment_id=new_run.environment_id,
                image_tag=env.image_tag,
                resource_limits=env.resource_limits,
                entrypoint="composition_runner.py",
                secret_names=secret_names,
            )
        except RuntimeError as e:
            logger.error(
                "Failed to create K8s job for resumed composition run %s: %s",
                new_run.id,
                e,
            )
            return self.run_service.mark_failed(
                new_run.id, error=f"Failed to create K8s job: {e}"
            )

        logger.info(
            "Resumed composition run %s from node %s as new run %s (K8s job %s)",
            run_id,
            from_node_id,
            new_run.id,
            job_name,
        )
        return new_run

    def _inject_cached_outputs(
        self,
        code: str,
        cached_outputs: dict[str, Any],
        from_node_id: str,
    ) -> str:
        """Inject cached outputs into generated code for resumed runs.

        Modifies the generated code to:
        1. Define cached outputs at the start of the function
        2. Skip execution for nodes with cached outputs

        Args:
            code: The original generated Python code
            cached_outputs: Dict mapping node IDs to their cached outputs
            from_node_id: The node ID to resume execution from

        Returns:
            Modified code with cached outputs injected
        """
        if not cached_outputs:
            return code

        # Build the cached outputs initialization code
        cached_lines = [
            "",
            "    # Cached outputs from previous run (partial re-run)",
            "    _cached_outputs = {",
        ]
        for node_id, output in cached_outputs.items():
            var_name = to_variable_name(node_id)
            try:
                output_repr = json.dumps(output)
            except (TypeError, ValueError):
                output_repr = repr(output)
            cached_lines.append(f'        "{node_id}": {output_repr},')
        cached_lines.append("    }")
        cached_lines.append("")

        # Build variable assignments for cached nodes
        for node_id in cached_outputs:
            var_name = to_variable_name(node_id)
            cached_lines.append(
                f'    {var_name}_output = _cached_outputs["{node_id}"]'
            )
        cached_lines.append("")
        cached_lines.append(f'    # Resuming execution from node: {from_node_id}')

        cached_code = "\n".join(cached_lines)

        # Find the insertion point (after the function docstring)
        lines = code.split("\n")
        insert_index = -1

        in_function = False
        for i, line in enumerate(lines):
            if line.strip().startswith("async def run_workflow") or line.strip().startswith("def run_workflow"):
                in_function = True
                continue
            if in_function and '"""' in line:
                # Found the closing docstring
                insert_index = i + 1
                break

        if insert_index == -1:
            # Fallback: insert after function definition
            for i, line in enumerate(lines):
                if line.strip().startswith("async def run_workflow") or line.strip().startswith("def run_workflow"):
                    insert_index = i + 1
                    break

        if insert_index == -1:
            # Last resort: prepend to code
            return cached_code + "\n" + code

        # Remove code generation for cached nodes (they'll use cached values)
        # We need to identify and remove the code blocks for cached nodes
        result_lines = lines[:insert_index]
        result_lines.append(cached_code)

        # Track which nodes to skip
        skip_nodes = set(cached_outputs.keys())

        # Process remaining lines, skipping code for cached nodes
        i = insert_index
        while i < len(lines):
            line = lines[i]

            # Check if this line starts a cached node's code block
            skip_this_block = False
            for node_id in skip_nodes:
                var_name = to_variable_name(node_id)
                # Check for comments or variable assignments related to this node
                if any(
                    marker in line
                    for marker in ["# Program:", "# Model:", "# Input:", "# Output:", "# Constant:"]
                ):
                    # Look ahead to see if the next line has this node's variable
                    if i + 1 < len(lines):
                        next_line = lines[i + 1]
                        if f"{var_name}_output" in next_line or f'log_node("{node_id}"' in next_line:
                            skip_this_block = True
                            break
                elif (
                    f'log_node("{node_id}"' in line
                    or (f"{var_name}_output = " in line and "cached_outputs" not in line)
                ):
                    skip_this_block = True
                    break

            if skip_this_block:
                # Skip until we hit an empty line or another node's code
                i += 1
                while i < len(lines) and lines[i].strip() and not lines[i].strip().startswith("#"):
                    # Check if this line is for a different node
                    is_different_node = False
                    for other_id in skip_nodes:
                        if other_id != node_id:
                            other_var = to_variable_name(other_id)
                            if f"{other_var}_output = " in lines[i]:
                                is_different_node = True
                                break
                    if is_different_node:
                        break
                    i += 1
                continue

            result_lines.append(line)
            i += 1

        return "\n".join(result_lines)

    def get_run(self, run_id: str) -> CompositionRun | None:
        """Get a composition run by ID.

        Args:
            run_id: Run's unique identifier

        Returns:
            CompositionRun if found, None otherwise
        """
        return self.run_service.get_run(run_id)

    def list_runs(
        self,
        owner_id: str | None = None,
        composition_id: str | None = None,
        status: RunExecutionStatus | None = None,
    ) -> list[CompositionRun]:
        """List composition runs with optional filtering.

        Args:
            owner_id: Filter by owner ID
            composition_id: Filter by composition ID
            status: Filter by status

        Returns:
            List of matching CompositionRuns
        """
        return self.run_service.list_runs(
            owner_id=owner_id,
            composition_id=composition_id,
            status=status,
        )


# =============================================================================
# Global Instances
# =============================================================================

_composition_run_service: CompositionRunService | None = None
_composition_executor: CompositionExecutor | None = None


def get_composition_run_service() -> CompositionRunService:
    """Get the global CompositionRunService instance."""
    global _composition_run_service
    if _composition_run_service is None:
        _composition_run_service = CompositionRunService()
    return _composition_run_service


def get_composition_executor() -> CompositionExecutor:
    """Get the global CompositionExecutor instance."""
    global _composition_executor
    if _composition_executor is None:
        _composition_executor = CompositionExecutor()
    return _composition_executor
