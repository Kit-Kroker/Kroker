//! The supervised Python bridge child and the frame-protocol client
//! (022 T018, contracts/bridge-protocol.md §Rust-side obligations).
//!
//! One child per MCP session, spawned on `initialized`. The child owns
//! the consecutive-wait streak and the actor's OperatorDeps; when it
//! dies, every in-flight call fails with the fixed internal sentence and
//! the next call respawns it lazily (the streak restarts at zero —
//! documented). No verb names appear here; the server branches only on
//! descriptor metadata (research R3).

use std::collections::HashMap;
use std::path::PathBuf;
use std::process::Stdio;
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::Duration;

use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::sync::Arc;
use tokio::io::{AsyncReadExt, AsyncWriteExt, BufReader};
use tokio::process::{Child, ChildStdin, ChildStdout, Command};
use tokio::sync::{Mutex, mpsc, oneshot};
use tracing::warn;

pub const BRIDGE_PROTOCOL: u64 = 1;
const MAX_FRAME_BYTES: usize = 4 * 1024 * 1024;
const HANDSHAKE_TIMEOUT: Duration = Duration::from_secs(20);

/// One tool descriptor as the Python `describe` frame publishes it
/// (data-model.md). The server maps it to `rmcp::model::Tool`.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ToolDescriptor {
    pub name: String,
    pub description: String,
    pub input_schema: Value,
    pub output_schema: Option<Value>,
    pub read_only: bool,
    pub confirm: String,
    pub progress: bool,
}

/// The preview the bridge returns for a confirm tool (PreviewResult).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PreviewResult {
    pub message: String,
    pub digest: String,
}

/// Every way a bridge request can end badly. The message strings are the
/// FIXED sentences from contracts/bridge-protocol.md — SC-003: nothing
/// else may reach the client.
#[derive(Debug, Clone)]
pub enum BridgeError {
    /// `error.code == "tool_error"`: carry `ToolError.message` verbatim.
    Tool(String),
    /// `error.code == "changed"`.
    Changed,
    /// `error.code == "cancelled"`.
    Cancelled,
    /// `error.code == "bad_request"`.
    BadRequest(String),
    /// `error.code == "internal"` — also the sentence for a dead child.
    Internal(String),
}

impl BridgeError {
    /// The fixed sentence for a dead child (SC-003: never a raw OS error).
    pub fn child_died() -> Self {
        BridgeError::Internal(internal_sentence())
    }

    pub fn message(&self) -> String {
        match self {
            BridgeError::Tool(m) | BridgeError::BadRequest(m) | BridgeError::Internal(m) => {
                m.clone()
            }
            BridgeError::Changed => CHANGED_SENTENCE.to_string(),
            BridgeError::Cancelled => "cancelled".to_string(),
        }
    }

    fn from_error_code(code: &str, message: String) -> BridgeError {
        match code {
            "tool_error" => BridgeError::Tool(message),
            "changed" => BridgeError::Changed,
            "cancelled" => BridgeError::Cancelled,
            "bad_request" => BridgeError::BadRequest(message),
            _ => BridgeError::Internal(message),
        }
    }
}

/// The fixed `changed` sentence, verbatim from contracts/bridge-protocol.md.
pub const CHANGED_SENTENCE: &str =
    "the pending item changed while you were confirming; re-read the inbox and retry";

/// The fixed `internal` sentence used when the child dies or a frame is
/// oversize/unparsable (bridge-protocol.md; the type token is stable so a
/// raw OS error can never reach the client).
pub fn internal_sentence() -> String {
    "the factory raised BridgeDied; the operator should check the server log".to_string()
}

struct Inner {
    child: Option<Child>,
    stdin: Option<ChildStdin>,
    pending: HashMap<String, oneshot::Sender<Value>>,
    progress: HashMap<String, mpsc::Sender<Value>>,
    describe_tx: Option<oneshot::Sender<Value>>,
    alive: bool,
}

/// The supervised Python child: one per MCP session, cloneable handle.
#[derive(Clone)]
pub struct Bridge {
    repo: PathBuf,
    bridge_cmd: Option<Vec<String>>,
    actor: String,
    state: Arc<Mutex<Inner>>,
    id_seq: std::sync::Arc<AtomicU64>,
}

impl Bridge {
    /// Spawn the bridge child and complete the init/describe handshake.
    /// `bridge_cmd` overrides the default
    /// `<repo>/.venv/bin/python -m sdlc.operator.bridge` (tests).
    pub async fn spawn(
        repo: PathBuf,
        bridge_cmd: Option<Vec<String>>,
        actor: &str,
    ) -> Result<(Bridge, Vec<ToolDescriptor>), String> {
        let bridge = Bridge {
            repo,
            bridge_cmd,
            actor: actor.to_string(),
            state: Arc::new(Mutex::new(Inner {
                child: None,
                stdin: None,
                pending: HashMap::new(),
                progress: HashMap::new(),
                describe_tx: None,
                alive: false,
            })),
            id_seq: std::sync::Arc::new(AtomicU64::new(0)),
        };
        let describe = bridge.start().await.map_err(|e| e.message())?;
        let tools: Vec<ToolDescriptor> =
            serde_json::from_value(describe.get("tools").cloned().unwrap_or(Value::Null))
                .map_err(|e| format!("describe frame did not validate: {e}"))?;
        Ok((bridge, tools))
    }

    /// A fresh bridge request id (server call sites use one per request).
    pub fn next_id(&self) -> String {
        format!("b{}", self.id_seq.fetch_add(1, Ordering::Relaxed))
    }

    fn command(&self) -> Command {
        let mut cmd = if let Some(argv) = &self.bridge_cmd {
            let mut it = argv.iter();
            let mut c = Command::new(it.next().cloned().unwrap_or_else(|| "python3".into()));
            c.args(it);
            c
        } else {
            #[cfg(windows)]
            let exe = self.repo.join(".venv/Scripts/python.exe");
            #[cfg(not(windows))]
            let exe = self.repo.join(".venv/bin/python");
            let exe = std::env::var("SDLC_MCP_PYTHON")
                .map(PathBuf::from)
                .unwrap_or(exe);
            let mut c = Command::new(exe);
            c.args(["-m", "sdlc.operator.bridge"]);
            c
        };
        cmd.current_dir(&self.repo);
        cmd.kill_on_drop(true);
        cmd.stdin(Stdio::piped()).stdout(Stdio::piped());
        cmd.stderr(Stdio::inherit());
        #[cfg(target_os = "linux")]
        {
            unsafe {
                cmd.pre_exec(|| {
                    // Die with the server: an orphaned bridge holds a
                    // poller open forever (research R6/S7).
                    libc::prctl(libc::PR_SET_PDEATHSIG, libc::SIGTERM, 0, 0, 0);
                    Ok(())
                });
            }
        }
        cmd
    }

    /// (Re)spawn the child and run the init handshake; returns describe.
    async fn start(&self) -> Result<Value, BridgeError> {
        let mut child = self
            .command()
            .spawn()
            .map_err(|e| BridgeError::Internal(format!("could not spawn the bridge child: {e}")))?;
        let stdin = child.stdin.take().expect("piped stdin");
        let stdout = child.stdout.take().expect("piped stdout");

        let state = self.state.clone();
        let describe_rx = {
            let (tx, rx) = oneshot::channel();
            let mut inner = state.lock().await;
            inner.child = Some(child);
            inner.stdin = Some(stdin);
            inner.alive = true;
            inner.describe_tx = Some(tx);
            rx
        };
        tokio::spawn(read_loop(stdout, state));

        let init = json!({
            "op": "init", "id": "init", "protocol": BRIDGE_PROTOCOL, "actor": self.actor
        });
        self.write_frame(&init).await?;
        let describe = tokio::time::timeout(HANDSHAKE_TIMEOUT, describe_rx)
            .await
            .map_err(|_| BridgeError::Internal("bridge handshake timed out".into()))?
            .map_err(|_| BridgeError::child_died())?;

        match describe.get("protocol").and_then(Value::as_u64) {
            Some(BRIDGE_PROTOCOL) => Ok(describe),
            other => Err(BridgeError::Internal(format!(
                "bridge protocol mismatch: {other:?}"
            ))),
        }
    }

    async fn ensure_started(&self) -> Result<(), BridgeError> {
        let alive = { self.state.lock().await.alive };
        if !alive {
            self.start().await.map(|_| ())?;
        }
        Ok(())
    }

    async fn write_frame(&self, frame: &Value) -> Result<(), BridgeError> {
        let mut line =
            serde_json::to_string(frame).map_err(|e| BridgeError::Internal(e.to_string()))?;
        line.push('\n');
        let mut inner = self.state.lock().await;
        let dead = BridgeError::child_died();
        let Some(stdin) = inner.stdin.as_mut() else {
            return Err(dead);
        };
        match stdin.write_all(line.as_bytes()).await {
            Ok(()) => stdin.flush().await.map_err(|_| BridgeError::child_died()),
            Err(_) => Err(BridgeError::child_died()),
        }
    }

    /// Register a terminal-frame receiver for `id`, send `frame`, wait.
    async fn roundtrip(&self, id: String, frame: Value) -> Result<Value, BridgeError> {
        self.ensure_started().await?;
        let rx = {
            let (tx, rx) = oneshot::channel();
            let mut inner = self.state.lock().await;
            inner.pending.insert(id.clone(), tx);
            rx
        };
        if let Err(e) = self.write_frame(&frame).await {
            self.state.lock().await.pending.remove(&id);
            return Err(e);
        }
        match rx.await {
            Ok(value) => frame_to_result(value),
            Err(_) => Err(BridgeError::child_died()),
        }
    }

    /// A pure-read preview for a confirm tool.
    pub async fn preview(
        &self,
        id: &str,
        tool: &str,
        args: &Value,
    ) -> Result<PreviewResult, BridgeError> {
        let frame = json!({"op": "preview", "id": id, "tool": tool, "args": args});
        let value = self.roundtrip(id.to_string(), frame).await?;
        serde_json::from_value(value)
            .map_err(|_| BridgeError::Internal("malformed preview frame".into()))
    }

    /// Run one tool call; `expect_digest` is required for confirm tools.
    pub async fn call(
        &self,
        id: &str,
        tool: &str,
        args: &Value,
        expect_digest: Option<&str>,
    ) -> Result<Value, BridgeError> {
        let mut frame = json!({"op": "call", "id": id, "tool": tool, "args": args});
        if let Some(digest) = expect_digest {
            frame["expect_digest"] = json!(digest);
        }
        self.roundtrip(id.to_string(), frame).await
    }

    /// Subscribe to progress frames for `id`; register before the call.
    pub async fn progress_sink(&self, id: &str) -> mpsc::Receiver<Value> {
        let (tx, rx) = mpsc::channel(16);
        self.state.lock().await.progress.insert(id.to_string(), tx);
        rx
    }

    /// Drop `id`'s progress sink once the call is done, so the forwarding
    /// task's receiver ends instead of leaking for the session's life.
    pub async fn drop_progress_sink(&self, id: &str) {
        self.state.lock().await.progress.remove(id);
    }

    /// Cancel an in-flight request by bridge id.
    pub async fn cancel(&self, id: &str) {
        let frame = json!({"op": "cancel", "id": id});
        let _ = self.write_frame(&frame).await;
    }
}

fn frame_to_result(frame: Value) -> Result<Value, BridgeError> {
    if frame.get("ok").and_then(Value::as_bool) == Some(true) {
        return Ok(frame.get("value").cloned().unwrap_or(Value::Null));
    }
    if !frame.is_object() {
        return Err(BridgeError::child_died());
    }
    let error = frame.get("error").cloned().unwrap_or(Value::Null);
    let code = error
        .get("code")
        .and_then(Value::as_str)
        .unwrap_or("internal");
    let message = error
        .get("message")
        .and_then(Value::as_str)
        .unwrap_or("bridge error without a message")
        .to_string();
    Err(BridgeError::from_error_code(code, message))
}

/// Fail every in-flight request with the internal sentence and mark the
/// child dead; the next call respawns lazily.
async fn child_died(state: &std::sync::Arc<Mutex<Inner>>) {
    let mut inner = state.lock().await;
    inner.alive = false;
    inner.stdin = None;
    if let Some(mut child) = inner.child.take() {
        let _ = child.start_kill();
    }
    inner.describe_tx = None;
    let sentence = serde_json::json!({
        "ok": false,
        "error": {"code": "internal", "message": internal_sentence()}
    });
    let pending: Vec<_> = inner.pending.drain().collect();
    inner.progress.clear();
    for (_, tx) in pending {
        let _ = tx.send(sentence.clone());
    }
}

/// The reader task: one line per frame, at most 4 MiB; oversize or
/// unparsable frames (or EOF) kill the child and fail in-flight calls.
///
/// A read may deliver several frames AND the start of the next one in a
/// single chunk, so complete lines are drained from a carry buffer and
/// the partial tail is kept for the next read (a partial tail parsed
/// early would be a false "unparsable frame").
async fn read_loop(stdout: ChildStdout, state: Arc<Mutex<Inner>>) {
    let mut reader = BufReader::with_capacity(64 * 1024, stdout);
    let mut carry: Vec<u8> = Vec::with_capacity(4096);
    let mut chunk = [0u8; 16 * 1024];
    loop {
        match reader.read(&mut chunk).await {
            Ok(0) => {
                warn!("bridge child stdout closed");
                child_died(&state).await;
                return;
            }
            Ok(n) => carry.extend_from_slice(&chunk[..n]),
            Err(e) => {
                warn!("bridge read error: {e}");
                child_died(&state).await;
                return;
            }
        }
        // Drain complete lines first: a full frame plus the start of the
        // next may legally share a chunk; only a PARTIAL line left in the
        // carry counts toward the per-frame cap.
        while let Some(pos) = carry.iter().position(|b| *b == b'\n') {
            let line: Vec<u8> = carry.drain(..=pos).collect();
            let line = &line[..line.len() - 1]; // strip the newline
            if line.is_empty() {
                continue;
            }
            let Ok(frame) = serde_json::from_slice::<Value>(line) else {
                warn!("unparsable bridge frame");
                child_died(&state).await;
                return;
            };
            let op = frame.get("op").and_then(Value::as_str).unwrap_or("");
            if op == "describe" {
                let mut inner = state.lock().await;
                if let Some(tx) = inner.describe_tx.take() {
                    let _ = tx.send(frame);
                }
                continue;
            }
            if op == "progress" {
                let id = frame
                    .get("id")
                    .and_then(Value::as_str)
                    .unwrap_or("")
                    .to_string();
                let sink = state.lock().await.progress.get(&id).cloned();
                if let Some(tx) = sink {
                    let _ = tx.send(frame).await;
                }
                continue;
            }
            // terminal frame: {"id": ..., "ok": ..., ...}
            let id = frame
                .get("id")
                .and_then(Value::as_str)
                .unwrap_or("")
                .to_string();
            let tx = state.lock().await.pending.remove(&id);
            if let Some(tx) = tx
                && tx.send(frame).is_err()
            {
                warn!("bridge terminal frame dropped: waiter {id} gone");
            }
        }
        // Whatever is left is a partial line: it may not exceed the cap.
        if carry.len() > MAX_FRAME_BYTES {
            warn!("bridge frame exceeded {} bytes", MAX_FRAME_BYTES);
            child_died(&state).await;
            return;
        }
    }
}
