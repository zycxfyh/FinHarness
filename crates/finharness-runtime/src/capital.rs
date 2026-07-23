//! FinHarness-specific public execution surface over the inherited transactional kernel.
//!
//! The kernel remains deliberately ignorant of capital semantics. This module narrows it to
//! pre-registered worker operations and binds every Job to a Principal, Agent runtime, domain
//! object, execution scope, context digest, and resource concurrency key.

use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, BTreeSet};
use std::fs;
use std::os::unix::fs::symlink;
use std::path::{Path, PathBuf};
use std::sync::{Arc, Mutex};

use crate::runtime::{
    Runtime, RuntimeConfig, RuntimeError, RuntimeErrorCode, RuntimeResult, TaskObservation,
    TaskRunRequest, UniversalExecutionRequest, RUNTIME_SCHEMA_VERSION,
};
use crate::universal::{
    canonical_directory, load_workspace_record, now_unix_ms, sha256_bytes, validate_id,
    validate_relative_path, write_json_atomic, UniversalExecutorConfig, WorkspaceRecord,
};

pub const CAPITAL_RUNTIME_SCHEMA_VERSION: u32 = 1;

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct ExecutionScope {
    pub scope_id: String,
    pub working_root: String,
    pub context_digest: String,
    pub resource_key: String,
}

#[derive(Clone, Debug)]
pub struct RegisteredOperation {
    pub executable: PathBuf,
    pub args_prefix: Vec<String>,
    pub cwd_relative: String,
    pub env: BTreeMap<String, String>,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct CapitalRunRequest {
    pub schema_version: u32,
    pub client_request_id: String,
    pub principal_id: String,
    pub agent_runtime_id: String,
    pub operation_kind: String,
    pub domain_ref: String,
    pub scope: ExecutionScope,
    pub input_path: String,
    pub global_limit: u32,
    pub timeout_ms: u64,
    pub stdout_limit_bytes: u64,
    pub stderr_limit_bytes: u64,
    pub wait_ms: u64,
    pub stdout_tail_bytes: u64,
    pub stderr_tail_bytes: u64,
}

#[derive(Clone, Debug)]
pub struct CapitalRuntimeConfig {
    pub runtime: RuntimeConfig,
    pub operations: BTreeMap<String, RegisteredOperation>,
}

#[derive(Clone, Debug)]
pub struct CapitalRuntime {
    runtime: Runtime,
    executor: UniversalExecutorConfig,
    operations: BTreeMap<String, RegisteredOperation>,
    lifecycle_lock: Arc<Mutex<()>>,
}

impl CapitalRuntime {
    pub fn new(config: CapitalRuntimeConfig) -> RuntimeResult<Self> {
        if config.operations.is_empty() {
            return Err(RuntimeError::invalid(
                "at least one registered operation is required",
                "operations",
            ));
        }
        for (kind, operation) in &config.operations {
            validate_id(kind, "operationKind").map_err(map_universal)?;
            validate_relative_path(&operation.cwd_relative, "cwdRelative")
                .map_err(map_universal)?;
            if !operation.executable.is_absolute() {
                return Err(RuntimeError::invalid(
                    "registered operation executable must be absolute",
                    "operations.executable",
                ));
            }
        }
        let executor = config.runtime.executor.clone();
        let runtime = Runtime::new(config.runtime)?;
        Ok(Self {
            runtime,
            executor,
            operations: config.operations,
            lifecycle_lock: Arc::new(Mutex::new(())),
        })
    }

    pub fn runtime(&self) -> &Runtime {
        &self.runtime
    }

    pub fn run(&self, request: &CapitalRunRequest) -> RuntimeResult<TaskObservation> {
        let _guard = self.lifecycle_lock.lock().map_err(|_| {
            RuntimeError::new(
                RuntimeErrorCode::RegistryUnavailable,
                "capital runtime lifecycle lock is poisoned",
                None,
                true,
            )
        })?;
        let task_request = self.build_task_request(request)?;
        self.runtime.run_task(&task_request)
    }

    pub fn build_task_request(&self, request: &CapitalRunRequest) -> RuntimeResult<TaskRunRequest> {
        validate_request(request)?;
        let operation = self
            .operations
            .get(&request.operation_kind)
            .ok_or_else(|| {
                RuntimeError::new(
                    RuntimeErrorCode::InvalidRequest,
                    "operationKind is not registered",
                    Some("operationKind"),
                    false,
                )
            })?;
        let working_root =
            canonical_directory(Path::new(&request.scope.working_root), "scope.workingRoot")
                .map_err(map_universal)?;
        let input_relative =
            validate_relative_path(&request.input_path, "inputPath").map_err(map_universal)?;
        let input_path = fs::canonicalize(working_root.join(input_relative)).map_err(|error| {
            RuntimeError::new(
                RuntimeErrorCode::InvalidRequest,
                format!("cannot resolve inputPath: {error}"),
                Some("inputPath"),
                false,
            )
        })?;
        if !input_path.starts_with(&working_root) || !input_path.is_file() {
            return Err(RuntimeError::new(
                RuntimeErrorCode::InvalidRequest,
                "inputPath must resolve to a file inside workingRoot",
                Some("inputPath"),
                false,
            ));
        }
        let internal_scope_id = internal_scope_id(&request.scope.resource_key);
        self.register_scope(
            &internal_scope_id,
            &working_root,
            &request.scope.context_digest,
        )?;

        let mut args = operation.args_prefix.clone();
        args.extend([
            "--operation-kind".to_string(),
            request.operation_kind.clone(),
            "--domain-ref".to_string(),
            request.domain_ref.clone(),
            "--principal-id".to_string(),
            request.principal_id.clone(),
            "--agent-runtime-id".to_string(),
            request.agent_runtime_id.clone(),
            "--input-path".to_string(),
            input_path.to_string_lossy().into_owned(),
        ]);
        Ok(TaskRunRequest {
            schema_version: RUNTIME_SCHEMA_VERSION,
            client_request_id: request.client_request_id.clone(),
            principal: request.principal_id.clone(),
            global_limit: request.global_limit,
            execution: UniversalExecutionRequest {
                workspace_id: internal_scope_id,
                executable: operation.executable.to_string_lossy().into_owned(),
                args,
                cwd_relative: operation.cwd_relative.clone(),
                env: operation.env.clone(),
                timeout_ms: request.timeout_ms,
                stdout_limit_bytes: request.stdout_limit_bytes,
                stderr_limit_bytes: request.stderr_limit_bytes,
            },
            wait_ms: request.wait_ms,
            stdout_tail_bytes: request.stdout_tail_bytes,
            stderr_tail_bytes: request.stderr_tail_bytes,
        })
    }

    fn register_scope(
        &self,
        internal_scope_id: &str,
        working_root: &Path,
        context_digest: &str,
    ) -> RuntimeResult<()> {
        self.executor.ensure_store().map_err(map_universal)?;
        let link = self.executor.workspaces_root().join(internal_scope_id);
        if link.exists() {
            let current = fs::canonicalize(&link).map_err(|error| {
                RuntimeError::new(
                    RuntimeErrorCode::IoError,
                    format!("cannot resolve registered execution scope: {error}"),
                    Some("scope.workingRoot"),
                    false,
                )
            })?;
            if current != working_root {
                return Err(RuntimeError::new(
                    RuntimeErrorCode::AttemptStateConflict,
                    "resourceKey is already bound to another workingRoot",
                    Some("scope.resourceKey"),
                    false,
                ));
            }
        } else {
            symlink(working_root, &link).map_err(|error| {
                RuntimeError::new(
                    RuntimeErrorCode::IoError,
                    format!("cannot register execution scope: {error}"),
                    Some("scope.workingRoot"),
                    false,
                )
            })?;
        }
        let record_path = self.executor.workspace_record_path(internal_scope_id);
        if record_path.exists() {
            let existing =
                load_workspace_record(&self.executor, internal_scope_id).map_err(map_universal)?;
            if existing.source_revision == context_digest {
                return Ok(());
            }
            let active = self
                .runtime
                .registry()
                .active_job_ids_for_workspace(internal_scope_id, 1)?;
            if !active.is_empty() {
                return Err(RuntimeError::new(
                    RuntimeErrorCode::WorkspaceBusy,
                    "execution scope context changed while a Job is active or held",
                    Some("scope.contextDigest"),
                    true,
                ));
            }
        }
        write_json_atomic(
            &record_path,
            &WorkspaceRecord {
                schema_version: crate::UNIVERSAL_EXEC_SCHEMA_VERSION,
                workspace_id: internal_scope_id.to_string(),
                source_repo: working_root.to_string_lossy().into_owned(),
                source_revision: context_digest.to_string(),
                workspace_path: working_root.to_string_lossy().into_owned(),
                created_unix_ms: now_unix_ms().map_err(map_universal)?,
            },
        )
        .map_err(map_universal)
    }
}

fn internal_scope_id(resource_key: &str) -> String {
    let digest = sha256_bytes(resource_key.as_bytes());
    format!("scope-{}", &digest["sha256:".len()..][..32])
}

fn validate_request(request: &CapitalRunRequest) -> RuntimeResult<()> {
    if request.schema_version != CAPITAL_RUNTIME_SCHEMA_VERSION {
        return Err(RuntimeError::invalid(
            "unsupported capital runtime schema version",
            "schemaVersion",
        ));
    }
    for (value, field) in [
        (&request.client_request_id, "clientRequestId"),
        (&request.principal_id, "principalId"),
        (&request.agent_runtime_id, "agentRuntimeId"),
    ] {
        validate_semantic_id(value, field)?;
    }
    for (value, field) in [
        (&request.operation_kind, "operationKind"),
        (&request.scope.scope_id, "scope.scopeId"),
    ] {
        validate_id(value, field).map_err(map_universal)?;
    }
    for (value, field, max) in [
        (&request.domain_ref, "domainRef", 256_usize),
        (&request.scope.context_digest, "scope.contextDigest", 256),
        (&request.scope.resource_key, "scope.resourceKey", 256),
    ] {
        if value.trim().is_empty() || value.len() > max || value.as_bytes().contains(&0) {
            return Err(RuntimeError::invalid(
                format!("{field} must be non-empty, bounded, and NUL-free"),
                field,
            ));
        }
    }
    if !Path::new(&request.scope.working_root).is_absolute() {
        return Err(RuntimeError::invalid(
            "scope.workingRoot must be absolute",
            "scope.workingRoot",
        ));
    }
    if request.global_limit == 0 {
        return Err(RuntimeError::invalid(
            "globalLimit must be positive",
            "globalLimit",
        ));
    }
    let semantic_args: BTreeSet<&str> = [
        request.operation_kind.as_str(),
        request.domain_ref.as_str(),
        request.principal_id.as_str(),
        request.agent_runtime_id.as_str(),
    ]
    .into_iter()
    .collect();
    if semantic_args
        .iter()
        .any(|value| value.contains('\n') || value.contains('\r'))
    {
        return Err(RuntimeError::invalid(
            "semantic identifiers cannot contain line breaks",
            "domainRef",
        ));
    }
    Ok(())
}

fn validate_semantic_id(value: &str, field: &str) -> RuntimeResult<()> {
    if value.trim().is_empty()
        || value.len() > 128
        || value.as_bytes().contains(&0)
        || value.chars().any(char::is_control)
    {
        return Err(RuntimeError::invalid(
            format!("{field} must be non-empty, bounded, and control-free"),
            field,
        ));
    }
    Ok(())
}

fn map_universal(error: crate::UniversalExecError) -> RuntimeError {
    RuntimeError::new(
        RuntimeErrorCode::InvalidRequest,
        error.to_string(),
        error.field.as_deref(),
        error.retryable,
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::{RegistryConfig, RuntimeConfig, UniversalExecutorConfig};
    use std::io::Write;
    use tempfile::TempDir;

    fn runtime(root: &TempDir) -> CapitalRuntime {
        let working = root.path().join("working");
        fs::create_dir_all(&working).unwrap();
        let runner = fs::canonicalize("/bin/true").unwrap();
        let operation = fs::canonicalize("/bin/echo").unwrap();
        let mut operations = BTreeMap::new();
        operations.insert(
            "paper_effect.execute".to_string(),
            RegisteredOperation {
                executable: operation,
                args_prefix: vec!["worker".to_string()],
                cwd_relative: ".".to_string(),
                env: BTreeMap::from([(
                    "PYTHONPATH".to_string(),
                    "/trusted/pythonpath".to_string(),
                )]),
            },
        );
        CapitalRuntime::new(CapitalRuntimeConfig {
            runtime: RuntimeConfig {
                registry: RegistryConfig {
                    db_path: root.path().join("runtime.sqlite"),
                    store_root: root.path().join("registry"),
                    busy_timeout_ms: 5_000,
                },
                executor: UniversalExecutorConfig {
                    store_root: root.path().join("executor"),
                    workspace_root: None,
                    workspace_uid: None,
                    workspace_gid: None,
                    runner_path: runner,
                    allowed_executable_roots: vec![PathBuf::from("/bin")],
                    max_runtime_ms: 60_000,
                    max_output_bytes: 1024 * 1024,
                },
                startup_grace_ms: 100,
            },
            operations,
        })
        .unwrap()
    }

    fn request(root: &TempDir) -> CapitalRunRequest {
        let working = root.path().join("working");
        let mut input = fs::File::create(working.join("input.json")).unwrap();
        input.write_all(b"{}").unwrap();
        CapitalRunRequest {
            schema_version: CAPITAL_RUNTIME_SCHEMA_VERSION,
            client_request_id: "effect.execute:12345678".to_string(),
            principal_id: "principal:test".to_string(),
            agent_runtime_id: "agent:test".to_string(),
            operation_kind: "paper_effect.execute".to_string(),
            domain_ref: "effect:123".to_string(),
            scope: ExecutionScope {
                scope_id: "effect.123".to_string(),
                working_root: working.to_string_lossy().into_owned(),
                context_digest: "capital-world:abc".to_string(),
                resource_key: "broker-account:paper".to_string(),
            },
            input_path: "input.json".to_string(),
            global_limit: 1,
            timeout_ms: 30_000,
            stdout_limit_bytes: 64 * 1024,
            stderr_limit_bytes: 64 * 1024,
            wait_ms: 0,
            stdout_tail_bytes: 4096,
            stderr_tail_bytes: 4096,
        }
    }

    #[test]
    fn registered_operation_hides_executable_and_environment_from_public_request() {
        let root = TempDir::new().unwrap();
        let runtime = runtime(&root);
        let built = runtime.build_task_request(&request(&root)).unwrap();
        assert_eq!(
            built.execution.env.get("PYTHONPATH").map(String::as_str),
            Some("/trusted/pythonpath")
        );
        assert!(built.execution.executable.ends_with("echo"));
        assert_eq!(built.execution.args[0], "worker");
        assert!(built.execution.args.contains(&"effect:123".to_string()));
    }

    #[test]
    fn unknown_operation_is_rejected_before_dispatch() {
        let root = TempDir::new().unwrap();
        let runtime = runtime(&root);
        let mut request = request(&root);
        request.operation_kind = "arbitrary.shell".to_string();
        let error = runtime.build_task_request(&request).unwrap_err();
        assert_eq!(error.code, RuntimeErrorCode::InvalidRequest);
    }

    #[test]
    fn resource_key_stably_owns_runtime_serialisation_scope() {
        assert_eq!(
            internal_scope_id("broker-account:paper"),
            internal_scope_id("broker-account:paper")
        );
        assert_ne!(
            internal_scope_id("broker-account:paper"),
            internal_scope_id("broker-account:other")
        );
    }
}
