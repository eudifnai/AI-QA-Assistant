use serde::{Deserialize, Serialize};
use std::io::{BufRead, BufReader};
use std::path::{Path, PathBuf};
use std::process::{Child, ChildStdout, Command, Stdio};
use std::sync::{mpsc, Mutex};
use std::time::Duration;
use tauri::{Manager, RunEvent, State};

#[cfg(target_os = "windows")]
use std::os::windows::process::CommandExt;

const BACKEND_STARTUP_TIMEOUT: Duration = Duration::from_secs(15);
const BACKEND_READY_MESSAGE: &str = "backend_ready";
#[cfg(target_os = "windows")]
const CREATE_NO_WINDOW: u32 = 0x0800_0000;

#[derive(Clone, Serialize)]
#[serde(rename_all = "camelCase")]
struct BackendConnection {
    base_url: String,
    token: String,
}

#[derive(Deserialize)]
struct BackendStartupMessage {
    #[serde(rename = "type")]
    message_type: String,
    port: u16,
    token: String,
}

struct BackendRuntime {
    connection: BackendConnection,
    child: Mutex<Option<Child>>,
}

impl BackendRuntime {
    fn shutdown(&self) {
        if let Ok(mut child_slot) = self.child.lock() {
            if let Some(mut child) = child_slot.take() {
                terminate_child(&mut child);
            }
        }
    }
}

impl Drop for BackendRuntime {
    fn drop(&mut self) {
        if let Ok(child_slot) = self.child.get_mut() {
            if let Some(mut child) = child_slot.take() {
                terminate_child(&mut child);
            }
        }
    }
}

fn terminate_child(child: &mut Child) {
    match child.try_wait() {
        Ok(Some(_)) => {}
        Ok(None) | Err(_) => {
            let _ = child.kill();
            let _ = child.wait();
        }
    }
}

fn find_workspace_root(start: &Path) -> Option<PathBuf> {
    start.ancestors().find_map(|candidate| {
        let backend_entry = candidate.join("backend").join("app").join("desktop.py");
        let project_file = candidate.join("pyproject.toml");
        (backend_entry.is_file() && project_file.is_file()).then(|| candidate.to_path_buf())
    })
}

fn resolve_workspace_root() -> Result<PathBuf, String> {
    if let Ok(executable) = std::env::current_exe() {
        if let Some(parent) = executable.parent() {
            if let Some(root) = find_workspace_root(parent) {
                return Ok(root);
            }
        }
    }
    if let Ok(current_directory) = std::env::current_dir() {
        if let Some(root) = find_workspace_root(&current_directory) {
            return Ok(root);
        }
    }
    Err("无法定位本地后端项目目录。".to_string())
}

fn python_executable(workspace_root: &Path) -> PathBuf {
    #[cfg(target_os = "windows")]
    {
        workspace_root
            .join(".venv")
            .join("Scripts")
            .join("python.exe")
    }
    #[cfg(not(target_os = "windows"))]
    {
        workspace_root.join(".venv").join("bin").join("python")
    }
}

fn read_startup_line(stdout: ChildStdout) -> Result<String, String> {
    let mut line = String::new();
    let bytes_read = BufReader::new(stdout)
        .read_line(&mut line)
        .map_err(|_| "无法读取本地后端启动信息。".to_string())?;
    if bytes_read == 0 {
        return Err("本地后端未返回启动信息。".to_string());
    }
    Ok(line)
}

fn parse_startup_message(line: &str) -> Result<BackendConnection, String> {
    let message: BackendStartupMessage =
        serde_json::from_str(line).map_err(|_| "本地后端启动信息格式无效。".to_string())?;
    if message.message_type != BACKEND_READY_MESSAGE
        || message.port < 1024
        || message.token.len() < 43
    {
        return Err("本地后端启动信息校验失败。".to_string());
    }
    Ok(BackendConnection {
        base_url: format!("http://127.0.0.1:{}", message.port),
        token: message.token,
    })
}

fn start_backend() -> Result<BackendRuntime, String> {
    let workspace_root = resolve_workspace_root()?;
    let python = python_executable(&workspace_root);
    if !python.is_file() {
        return Err("项目 Python 虚拟环境不存在，请先运行 uv sync。".to_string());
    }

    let mut command = Command::new(python);
    let parent_pid = std::process::id().to_string();
    command
        .args(["-m", "backend.app.desktop", "--parent-pid"])
        .arg(parent_pid)
        .current_dir(&workspace_root)
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::inherit());
    #[cfg(target_os = "windows")]
    command.creation_flags(CREATE_NO_WINDOW);

    let mut child = command
        .spawn()
        .map_err(|_| "无法启动本地后端进程。".to_string())?;
    let stdout = match child.stdout.take() {
        Some(stdout) => stdout,
        None => {
            terminate_child(&mut child);
            return Err("无法建立本地后端安全握手通道。".to_string());
        }
    };
    let (sender, receiver) = mpsc::sync_channel(1);
    std::thread::spawn(move || {
        let _ = sender.send(read_startup_line(stdout));
    });

    let startup_line = match receiver.recv_timeout(BACKEND_STARTUP_TIMEOUT) {
        Ok(Ok(line)) => line,
        Ok(Err(error)) => {
            terminate_child(&mut child);
            return Err(error);
        }
        Err(_) => {
            terminate_child(&mut child);
            return Err("等待本地后端启动超时。".to_string());
        }
    };
    let connection = match parse_startup_message(&startup_line) {
        Ok(connection) => connection,
        Err(error) => {
            terminate_child(&mut child);
            return Err(error);
        }
    };

    Ok(BackendRuntime {
        connection,
        child: Mutex::new(Some(child)),
    })
}

#[tauri::command]
fn get_backend_connection(runtime: State<'_, BackendRuntime>) -> BackendConnection {
    runtime.connection.clone()
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let app = tauri::Builder::default()
        .setup(|app| {
            let runtime = start_backend().map_err(std::io::Error::other)?;
            app.manage(runtime);
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![get_backend_connection])
        .build(tauri::generate_context!())
        .expect("failed to build AI QA Assistant");

    app.run(|app_handle, event| {
        if matches!(event, RunEvent::Exit) {
            if let Some(runtime) = app_handle.try_state::<BackendRuntime>() {
                runtime.shutdown();
            }
        }
    });
}

#[cfg(test)]
mod tests {
    use super::{find_workspace_root, parse_startup_message};
    use std::path::Path;

    #[test]
    fn parses_valid_loopback_connection() {
        let token = "abcdefghijklmnopqrstuvwxyz0123456789ABCDEFG";
        let line = format!(r#"{{"type":"backend_ready","port":54321,"token":"{token}"}}"#);

        let connection = parse_startup_message(&line).expect("startup message should be valid");

        assert_eq!(connection.base_url, "http://127.0.0.1:54321");
        assert_eq!(connection.token, token);
    }

    #[test]
    fn rejects_short_session_token() {
        let line = r#"{"type":"backend_ready","port":54321,"token":"too-short"}"#;

        assert!(parse_startup_message(line).is_err());
    }

    #[test]
    fn locates_workspace_from_tauri_manifest() {
        let root = find_workspace_root(Path::new(env!("CARGO_MANIFEST_DIR")))
            .expect("workspace root should be discoverable");

        assert!(root
            .join("backend")
            .join("app")
            .join("desktop.py")
            .is_file());
    }
}
