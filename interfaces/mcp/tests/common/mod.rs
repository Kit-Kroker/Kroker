//! The shared in-process test harness (022): a scripted rmcp client, the
//! duplex-transport server spawner (SDK-driven and raw), and the small
//! frame/record helpers every section file uses. Section files declare
//! `mod common;` — the standard cargo integration-test pattern.

#![allow(dead_code)]

use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::{Arc, Mutex};
use std::time::Duration;

use rmcp::model::{
    CallToolRequestParams, CallToolResult, ClientConfig, ContentBlock, ElicitRequestParams,
    ElicitResult, ElicitationAction, ElicitationCapability, FormElicitationCapability,
    Implementation, ProgressNotificationParam, ProtocolVersion,
};
use rmcp::service::NotificationContext;
use rmcp::service::{RequestContext, RoleClient};
use rmcp::{ClientHandler, ErrorData as McpError, ServiceExt};
use serde_json::{Value, json};

use kroker_mcp::server::{Server, ServerConfig};

pub static DIR_SEQ: AtomicUsize = AtomicUsize::new(0);

// ---- the scripted client -------------------------------------------------

/// What the client answers when the server elicits (T028's confirm tests
/// script every variant).
#[derive(Clone, Debug, PartialEq)]
pub enum ElicitAnswer {
    /// accept, carrying `confirm`.
    Accept(bool),
    Decline,
    /// The request dies (as a client-side cancel would).
    Abort,
    /// Never answers: the server's elicitation timeout is the only way out.
    /// Used with `tokio::time::pause` so 300 s costs nothing.
    Hang,
}

/// A test clock: unix seconds with a mutable offset (T029 expiry).
pub type Clock = Arc<dyn Fn() -> u64 + Send + Sync>;

#[derive(Clone)]
pub struct TestClient {
    pub elicitation: bool,
    /// The protocol version this client proposes: LATEST negotiates E2
    /// (>= 2026-07-28), V_2025_11_25 negotiates E1.
    version: ProtocolVersion,
    pub answer: Arc<Mutex<ElicitAnswer>>,
    pub elicited: Arc<Mutex<Vec<ElicitRequestParams>>>,
    pub progress: Arc<Mutex<Vec<ProgressNotificationParam>>>,
    pub cancelled: Arc<Mutex<Vec<Value>>>,
}

impl TestClient {
    pub fn new(elicitation: bool) -> Self {
        Self::new_versioned(elicitation, ProtocolVersion::LATEST)
    }

    pub fn new_versioned(elicitation: bool, version: ProtocolVersion) -> Self {
        Self {
            elicitation,
            version,
            answer: Arc::new(Mutex::new(ElicitAnswer::Accept(true))),
            elicited: Arc::new(Mutex::new(Vec::new())),
            progress: Arc::new(Mutex::new(Vec::new())),
            cancelled: Arc::new(Mutex::new(Vec::new())),
        }
    }

    pub fn set_answer(&self, answer: ElicitAnswer) {
        *self.answer.lock().unwrap() = answer;
    }
}

impl ClientHandler for TestClient {
    fn get_info(&self) -> ClientConfig {
        let mut info = ClientConfig::default();
        info.client_info = Implementation::new("parity-client", "0.0.0");
        info.protocol_version = self.version.clone();
        if self.elicitation {
            let mut elic = ElicitationCapability::default();
            elic.form = Some(FormElicitationCapability::default());
            info.capabilities.elicitation = Some(elic);
        }
        info
    }

    async fn create_elicitation(
        &self,
        request: ElicitRequestParams,
        _context: RequestContext<RoleClient>,
    ) -> Result<ElicitResult, McpError> {
        self.elicited.lock().unwrap().push(request);
        let answer = self.answer.lock().unwrap().clone();
        match answer {
            ElicitAnswer::Accept(confirm) => Ok(ElicitResult::new(ElicitationAction::Accept)
                .with_content(json!({ "confirm": confirm }))),
            ElicitAnswer::Decline => Ok(ElicitResult::new(ElicitationAction::Decline)),
            ElicitAnswer::Abort => Err(McpError::new(
                rmcp::model::ErrorCode::INTERNAL_ERROR,
                "elicitation aborted by test client",
                None,
            )),
            ElicitAnswer::Hang => {
                // The server's elicitation timeout is the only way this
                // resolves; paired with paused time so 300 s is instant.
                std::future::pending::<()>().await;
                unreachable!("a hanging elicitation never resolves")
            }
        }
    }

    fn on_progress(
        &self,
        params: ProgressNotificationParam,
        _context: NotificationContext<RoleClient>,
    ) -> impl Future<Output = ()> + Send + '_ {
        let log = self.progress.clone();
        async move {
            log.lock().unwrap().push(params);
        }
    }

    fn on_cancelled(
        &self,
        params: rmcp::model::CancelledNotificationParam,
        _context: NotificationContext<RoleClient>,
    ) -> impl Future<Output = ()> + Send + '_ {
        let log = self.cancelled.clone();
        async move {
            log.lock()
                .unwrap()
                .push(serde_json::to_value(&params).unwrap_or(Value::Null));
        }
    }
}

// ---- the harness ----------------------------------------------------------

// ---- the harness ----------------------------------------------------------

pub struct Harness {
    pub client: rmcp::service::RunningService<RoleClient, TestClient>,
    pub record: PathBuf,
    #[allow(dead_code)]
    server: tokio::task::JoinHandle<()>,
}

pub fn temp_case(name: &str) -> PathBuf {
    let dir = std::env::temp_dir().join(format!(
        "kroker-mcp-{}-{}-{}",
        name,
        std::process::id(),
        DIR_SEQ.fetch_add(1, Ordering::SeqCst)
    ));
    std::fs::create_dir_all(&dir).unwrap();
    dir
}

pub async fn start(name: &str, scenario: Value) -> Harness {
    start_cfg(name, scenario, TestClient::new(true), None).await
}

pub async fn start_cfg(
    name: &str,
    mut scenario: Value,
    client: TestClient,
    now: Option<Clock>,
) -> Harness {
    let dir = temp_case(name);
    let record = dir.join("record.jsonl");
    scenario["record_path"] = json!(record.to_string_lossy());
    let scenario_path = dir.join("scenario.json");
    std::fs::write(&scenario_path, serde_json::to_string(&scenario).unwrap()).unwrap();

    let manifest_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    let bridge_cmd = vec![
        "python3".to_string(),
        manifest_dir
            .join("tests/fixtures/fake_bridge.py")
            .to_string_lossy()
            .into_owned(),
        scenario_path.to_string_lossy().into_owned(),
    ];
    let cfg = ServerConfig {
        repo: manifest_dir.join("../.."),
        bridge_cmd: Some(bridge_cmd),
        actor_override: None,
        now,
    };

    let (server_side, client_side) = tokio::io::duplex(64 * 1024);
    let server = tokio::spawn(async move {
        let svc = Server::new(cfg).serve(server_side).await.expect("serve");
        svc.waiting().await.expect("wait");
    });
    let client = client.serve(client_side).await.expect("client");
    Harness {
        client,
        record,
        server,
    }
}

pub fn record_lines(path: &Path) -> Vec<Value> {
    let text = std::fs::read_to_string(path).unwrap_or_default();
    text.lines()
        .filter(|l| !l.trim().is_empty())
        .map(|l| serde_json::from_str(l).expect("record jsonl"))
        .collect()
}

pub async fn call(
    client: &rmcp::service::RunningService<RoleClient, TestClient>,
    tool: &str,
) -> CallToolResult {
    tokio::time::timeout(
        Duration::from_secs(15),
        client.call_tool(CallToolRequestParams::new(tool.to_string())),
    )
    .await
    .expect("call timed out (handler todo!() panic closes the transport)")
    .expect("call_tool protocol error")
}

pub fn single_text(result: &CallToolResult) -> String {
    assert_eq!(result.content.len(), 1, "one content block");
    match &result.content[0] {
        ContentBlock::Text(t) => t.text.to_string(),
        other => panic!("expected text block, got {other:?}"),
    }
}

pub fn with_args(tool: &str, args: Value) -> CallToolRequestParams {
    CallToolRequestParams::new(tool.to_string())
        .with_arguments(args.as_object().cloned().unwrap_or_default())
}

/// Poll (real time) until the fake bridge records one op — used by the
/// timeout test to freeze the clock only after the preview roundtrip has
/// completed, so no subprocess I/O is pending under paused time.
pub async fn wait_for_recorded_op(path: &Path, op: &str) {
    for _ in 0..1000 {
        if record_lines(path).iter().any(|r| r["op"] == op) {
            return;
        }
        tokio::time::sleep(Duration::from_millis(10)).await;
    }
    panic!("{op} never reached the bridge");
}

// ---- the raw JSON-RPC driver ----------------------------------------------

/// A raw JSON-RPC driver: rmcp's client-side cancellation API is
/// crate-private and it auto-attaches a progress token to every request,
/// so the "no token" and "cancel" cases drive the transport by hand.
pub async fn start_raw(name: &str, mut scenario: Value) -> (tokio::io::DuplexStream, PathBuf) {
    let dir = temp_case(name);
    let record = dir.join("record.jsonl");
    scenario["record_path"] = json!(record.to_string_lossy());
    let scenario_path = dir.join("scenario.json");
    std::fs::write(&scenario_path, serde_json::to_string(&scenario).unwrap()).unwrap();
    let manifest_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    let cfg = ServerConfig {
        repo: manifest_dir.join("../.."),
        bridge_cmd: Some(vec![
            "python3".to_string(),
            manifest_dir
                .join("tests/fixtures/fake_bridge.py")
                .to_string_lossy()
                .into_owned(),
            scenario_path.to_string_lossy().into_owned(),
        ]),
        actor_override: None,
        now: None,
    };
    let (server_side, client_side) = tokio::io::duplex(64 * 1024);
    tokio::spawn(async move {
        let svc = Server::new(cfg).serve(server_side).await.expect("serve");
        svc.waiting().await.expect("wait");
    });
    (client_side, record)
}

/// Write one JSON-RPC frame; read one line back (raw driver helpers).
pub async fn send_raw(w: &mut tokio::io::WriteHalf<tokio::io::DuplexStream>, frame: Value) {
    use tokio::io::AsyncWriteExt;
    let mut data = serde_json::to_string(&frame).unwrap();
    data.push('\n');
    w.write_all(data.as_bytes()).await.unwrap();
}

pub async fn read_raw(
    lines: &mut tokio::io::BufReader<tokio::io::ReadHalf<tokio::io::DuplexStream>>,
) -> Value {
    use tokio::io::AsyncBufReadExt;
    let mut line = String::new();
    lines.read_line(&mut line).await.unwrap();
    serde_json::from_str(line.trim()).expect("line json")
}
