use finharness_runtime::{
    ArtifactReadRequest, CapitalRunRequest, CapitalRuntime, CapitalRuntimeConfig,
    RegisteredOperation, RegistryConfig, RuntimeConfig, RuntimeError, RuntimeJobListRequest,
    TaskCancelRequest, TaskObserveRequest, UniversalExecutorConfig,
};
use serde::de::DeserializeOwned;
use serde::Serialize;
use serde_json::json;
use std::collections::BTreeMap;
use std::env;
use std::fs;
use std::io::{self, Read};
use std::path::{Path, PathBuf};

fn main() {
    if let Err(error) = run() {
        let payload = serde_json::to_string(&error).unwrap_or_else(|_| {
            json!({"code":"RUNTIME_ERROR","message":error.to_string()}).to_string()
        });
        eprintln!("{payload}");
        std::process::exit(1);
    }
}

fn run() -> Result<(), RuntimeError> {
    let command = env::args().nth(1).ok_or_else(|| {
        RuntimeError::invalid(
            "expected one command: run, observe, cancel, list, or artifact-read",
            "command",
        )
    })?;
    let runtime = runtime_from_env()?;
    match command.as_str() {
        "run" => print_json(&runtime.run(&read_json::<CapitalRunRequest>()?)),
        "observe" => print_json(
            &runtime
                .runtime()
                .observe_task(&read_json::<TaskObserveRequest>()?),
        ),
        "cancel" => print_json(
            &runtime
                .runtime()
                .cancel_task(&read_json::<TaskCancelRequest>()?),
        ),
        "list" => print_json(
            &runtime
                .runtime()
                .list_jobs(&read_json::<RuntimeJobListRequest>()?),
        ),
        "artifact-read" => print_json(
            &runtime
                .runtime()
                .read_artifact(&read_json::<ArtifactReadRequest>()?),
        ),
        _ => Err(RuntimeError::invalid("unknown runtime command", "command")),
    }
}

fn runtime_from_env() -> Result<CapitalRuntime, RuntimeError> {
    let root = required_path("FINHARNESS_RUNTIME_ROOT")?;
    let runner = canonical_file(&required_path("FINHARNESS_RUNTIME_RUNNER")?, "runner")?;
    let python = canonical_file(
        &required_path("FINHARNESS_RUNTIME_WORKER_PYTHON")?,
        "python",
    )?;
    let python_root = python
        .parent()
        .ok_or_else(|| {
            RuntimeError::invalid("worker Python has no parent directory", "workerPython")
        })?
        .to_path_buf();
    let worker_pythonpath = env::var("FINHARNESS_RUNTIME_WORKER_PYTHONPATH").map_err(|_| {
        RuntimeError::invalid(
            "missing required environment variable FINHARNESS_RUNTIME_WORKER_PYTHONPATH",
            "workerPythonPath",
        )
    })?;
    let operations = BTreeMap::from([(
        "paper_effect.execute".to_string(),
        RegisteredOperation {
            executable: python,
            args_prefix: vec!["-m".to_string(), "finharness.runtime_worker".to_string()],
            cwd_relative: ".".to_string(),
            env: BTreeMap::from([("PYTHONPATH".to_string(), worker_pythonpath)]),
        },
    )]);
    CapitalRuntime::new(CapitalRuntimeConfig {
        runtime: RuntimeConfig {
            registry: RegistryConfig {
                db_path: root.join("runtime.sqlite"),
                store_root: root.join("registry"),
                busy_timeout_ms: env_u64("FINHARNESS_RUNTIME_BUSY_TIMEOUT_MS", 5_000)?,
            },
            executor: UniversalExecutorConfig {
                store_root: root.join("executor"),
                workspace_root: None,
                workspace_uid: None,
                workspace_gid: None,
                runner_path: runner,
                allowed_executable_roots: vec![python_root],
                max_runtime_ms: env_u64("FINHARNESS_RUNTIME_MAX_MS", 24 * 60 * 60 * 1000)?,
                max_output_bytes: env_u64("FINHARNESS_RUNTIME_MAX_OUTPUT_BYTES", 64 * 1024 * 1024)?,
            },
            startup_grace_ms: env_u64("FINHARNESS_RUNTIME_STARTUP_GRACE_MS", 1_000)?,
        },
        operations,
    })
}

fn required_path(name: &str) -> Result<PathBuf, RuntimeError> {
    let raw = env::var(name).map_err(|_| {
        RuntimeError::invalid(
            format!("missing required environment variable {name}"),
            name,
        )
    })?;
    let path = PathBuf::from(raw);
    if !path.is_absolute() {
        return Err(RuntimeError::invalid(
            format!("{name} must be an absolute path"),
            name,
        ));
    }
    Ok(path)
}

fn canonical_file(path: &Path, field: &str) -> Result<PathBuf, RuntimeError> {
    let canonical = fs::canonicalize(path).map_err(|error| {
        RuntimeError::invalid(format!("cannot canonicalize {field}: {error}"), field)
    })?;
    if !canonical.is_file() {
        return Err(RuntimeError::invalid(
            format!("{field} must be a file"),
            field,
        ));
    }
    Ok(canonical)
}

fn env_u64(name: &str, default: u64) -> Result<u64, RuntimeError> {
    match env::var(name) {
        Ok(value) => value.parse::<u64>().map_err(|_| {
            RuntimeError::invalid(format!("{name} must be an unsigned integer"), name)
        }),
        Err(_) => Ok(default),
    }
}

fn read_json<T: DeserializeOwned>() -> Result<T, RuntimeError> {
    let mut input = String::new();
    io::stdin()
        .read_to_string(&mut input)
        .map_err(|error| RuntimeError::invalid(format!("cannot read stdin: {error}"), "stdin"))?;
    serde_json::from_str(&input)
        .map_err(|error| RuntimeError::invalid(format!("invalid JSON request: {error}"), "stdin"))
}

fn print_json<T: Serialize>(result: &Result<T, RuntimeError>) -> Result<(), RuntimeError> {
    match result {
        Ok(value) => {
            println!(
                "{}",
                serde_json::to_string(value).map_err(|error| {
                    RuntimeError::invalid(format!("cannot serialize response: {error}"), "response")
                })?
            );
            Ok(())
        }
        Err(error) => Err(error.clone()),
    }
}
