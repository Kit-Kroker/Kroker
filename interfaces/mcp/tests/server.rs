//! In-process rmcp client tests against the server over a duplex
//! transport, with `--bridge-cmd` pointing at the scripted fake bridge
//! (tests/fixtures/fake_bridge.py) — 022 T017.
//!
//! Red phase: list/call paths hit the server's `todo!()` stubs, so these
//! tests fail at runtime for the expected reason (the panic surfaces as
//! the transport closing under the client). `verb_names_absent` passes
//! from day one: no Rust source under src/ may name one of the twelve
//! verbs (research R3/S3).

use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::{Arc, Mutex};
use std::time::Duration;

use rmcp::model::{
    CallToolRequestParams, CallToolResponse, CallToolResult, ClientConfig, ContentBlock,
    ElicitRequestParams, ElicitResult, ElicitationAction, ElicitationCapability,
    FormElicitationCapability, Implementation, ProgressNotificationParam, ProtocolVersion,
};
use rmcp::service::NotificationContext;
use rmcp::service::{RequestContext, RoleClient};
use rmcp::{ClientHandler, ErrorData as McpError, ServiceExt};
use serde_json::{Value, json};

use kroker_mcp::server::{Server, ServerConfig};

static DIR_SEQ: AtomicUsize = AtomicUsize::new(0);

// ---- the scripted client -------------------------------------------------

/// What the client answers when the server elicits (T028's confirm tests
/// script every variant).
#[derive(Clone, Debug, PartialEq)]
enum ElicitAnswer {
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
type Clock = Arc<dyn Fn() -> u64 + Send + Sync>;

#[derive(Clone)]
struct TestClient {
    elicitation: bool,
    /// The protocol version this client proposes: LATEST negotiates E2
    /// (>= 2026-07-28), V_2025_11_25 negotiates E1.
    version: ProtocolVersion,
    answer: Arc<Mutex<ElicitAnswer>>,
    elicited: Arc<Mutex<Vec<ElicitRequestParams>>>,
    progress: Arc<Mutex<Vec<ProgressNotificationParam>>>,
    cancelled: Arc<Mutex<Vec<Value>>>,
}

impl TestClient {
    fn new(elicitation: bool) -> Self {
        Self::new_versioned(elicitation, ProtocolVersion::LATEST)
    }

    fn new_versioned(elicitation: bool, version: ProtocolVersion) -> Self {
        Self {
            elicitation,
            version,
            answer: Arc::new(Mutex::new(ElicitAnswer::Accept(true))),
            elicited: Arc::new(Mutex::new(Vec::new())),
            progress: Arc::new(Mutex::new(Vec::new())),
            cancelled: Arc::new(Mutex::new(Vec::new())),
        }
    }

    fn set_answer(&self, answer: ElicitAnswer) {
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

struct Harness {
    client: rmcp::service::RunningService<RoleClient, TestClient>,
    record: PathBuf,
    #[allow(dead_code)]
    server: tokio::task::JoinHandle<()>,
}

fn temp_case(name: &str) -> PathBuf {
    let dir = std::env::temp_dir().join(format!(
        "kroker-mcp-{}-{}-{}",
        name,
        std::process::id(),
        DIR_SEQ.fetch_add(1, Ordering::SeqCst)
    ));
    std::fs::create_dir_all(&dir).unwrap();
    dir
}

async fn start(name: &str, scenario: Value) -> Harness {
    start_cfg(name, scenario, TestClient::new(true), None).await
}

async fn start_cfg(
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

fn record_lines(path: &Path) -> Vec<Value> {
    let text = std::fs::read_to_string(path).unwrap_or_default();
    text.lines()
        .filter(|l| !l.trim().is_empty())
        .map(|l| serde_json::from_str(l).expect("record jsonl"))
        .collect()
}

async fn call(
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

fn single_text(result: &CallToolResult) -> String {
    assert_eq!(result.content.len(), 1, "one content block");
    match &result.content[0] {
        ContentBlock::Text(t) => t.text.to_string(),
        other => panic!("expected text block, got {other:?}"),
    }
}

// ---- section: list ---------------------------------------------------------

#[tokio::test]
async fn tools_list_mirrors_describe_names_and_annotations() {
    let h = start("list-mirrors", json!({})).await;
    let tools = tokio::time::timeout(Duration::from_secs(15), h.client.list_tools(None))
        .await
        .expect("list timed out (todo!() panic)")
        .expect("list_tools protocol error");

    let names: Vec<String> = tools.tools.iter().map(|t| t.name.to_string()).collect();
    let expected = [
        "list_runs",
        "get_run",
        "follow",
        "inbox",
        "list_projects",
        "get_project",
        "list_tasks",
        "project_events",
        "read_artifact",
        "start_run",
        "answer_question",
        "decide_gate",
    ];
    assert_eq!(names, expected, "twelve verbs in describe order");
    for tool in &tools.tools {
        let ann = tool.annotations.as_ref().expect("annotations present");
        let is_write = !expected[..9].contains(&tool.name.as_ref());
        assert_eq!(
            ann.read_only_hint,
            Some(!is_write),
            "{} read_only",
            tool.name
        );
        if is_write {
            assert_eq!(
                ann.destructive_hint,
                Some(true),
                "{} destructive",
                tool.name
            );
            assert_eq!(ann.idempotent_hint, Some(false), "{} idempotent", tool.name);
        }
        assert_eq!(ann.open_world_hint, Some(false), "{} open_world", tool.name);
        assert!(
            tool.description.as_deref().unwrap_or("").contains("canned"),
            "{} description",
            tool.name
        );
    }
}

#[tokio::test]
async fn a_text_result_maps_to_one_text_block() {
    let h = start(
        "call-text",
        json!({"call": [{"frame": {"ok": true, "value": "two open runs, one gate"}}]}),
    )
    .await;
    let result = call(&h.client, "inbox").await;
    assert_ne!(result.is_error, Some(true));
    assert_eq!(single_text(&result), "two open runs, one gate");
    assert!(result.structured_content.is_none());
}

#[tokio::test]
async fn an_object_result_maps_to_structured_content_plus_json_text() {
    let value = json!({"run_id": "feature-add-sso", "key": "architecture#2", "confirmed": true, "detail": "approved"});
    let h = start(
        "call-object",
        json!({"call": [{"frame": {"ok": true, "value": value}}]}),
    )
    .await;
    let result = call(&h.client, "read_artifact").await;
    assert_ne!(result.is_error, Some(true));
    assert_eq!(result.structured_content.as_ref(), Some(&value));
    assert_eq!(
        single_text(&result),
        serde_json::to_string(&value).unwrap(),
        "the text block carries the same JSON for clients without structuredContent"
    );
}

#[tokio::test]
async fn a_tool_error_maps_to_is_error_with_the_verbatim_message() {
    let h = start(
        "call-error",
        json!({"call": [{"frame": {"ok": false, "error": {"code": "tool_error", "message": "no run 'nope' among 2 open and 0 recently closed runs; call list_runs"}}}]}),
    )
    .await;
    let result = call(&h.client, "get_run").await;
    assert_eq!(result.is_error, Some(true));
    assert_eq!(
        single_text(&result),
        "no run 'nope' among 2 open and 0 recently closed runs; call list_runs"
    );
}

// ---- section: supervisor ---------------------------------------------------

const INTERNAL_SENTENCE: &str =
    "the factory raised BridgeDied; the operator should check the server log";

#[tokio::test]
async fn an_oversize_frame_fails_the_call_and_the_next_call_respawns() {
    let oversize = "x".repeat(4 * 1024 * 1024 + 64);
    let h = start(
        "supervisor-oversize",
        json!({
            "call": [
                {"lines": [oversize]},
                {"frame": {"ok": true, "value": "back after respawn"}}
            ]
        }),
    )
    .await;

    let first = call(&h.client, "inbox").await;
    assert_eq!(
        first.is_error,
        Some(true),
        "the oversize frame kills the child"
    );
    assert_eq!(single_text(&first), INTERNAL_SENTENCE);

    let second = call(&h.client, "inbox").await;
    assert_ne!(second.is_error, Some(true), "lazy respawn on the next call");
    assert_eq!(single_text(&second), "back after respawn");

    let inits = record_lines(&h.record)
        .into_iter()
        .filter(|r| r["op"] == "init")
        .count();
    assert_eq!(inits, 2, "the child died and was respawned");
}

#[tokio::test]
async fn a_mid_call_exit_fails_with_internal_then_respawns() {
    let h = start(
        "supervisor-exit",
        json!({
            "call": [
                {"exit": 9},
                {"frame": {"ok": true, "value": "third time lucky"}}
            ]
        }),
    )
    .await;

    let first = call(&h.client, "inbox").await;
    assert_eq!(first.is_error, Some(true));
    assert_eq!(single_text(&first), INTERNAL_SENTENCE);

    let second = call(&h.client, "inbox").await;
    assert_ne!(second.is_error, Some(true));
    assert_eq!(single_text(&second), "third time lucky");

    let inits = record_lines(&h.record)
        .into_iter()
        .filter(|r| r["op"] == "init")
        .count();
    assert_eq!(inits, 2);
}

// ---- section: confirm (T028) ----------------------------------------------
//
// Every test name carries "confirm" so `cargo test confirm` selects the
// section. RED state against the T028 stub: every case that needs the
// elicitation handshake (accept, decline/cancel/timeout sentences, all of
// E2, the bridge-error mappings) fails because the stub answers the
// no-confirmation sentence and never reaches the bridge; the fail-closed
// no-capability case passes from day one.

use kroker_mcp::bridge::CHANGED_SENTENCE;
use kroker_mcp::confirm::{DID_NOT_CONFIRM_SENTENCE, INVALID_SENTENCE};
use kroker_mcp::server::NO_CONFIRMATION_SENTENCE;

/// Decision-ish args for the confirm verbs; the fake bridge records them
/// verbatim and answers the canned preview (digest "0" * 64).
fn gate_args() -> Value {
    json!({"run_id": "feature-add-sso", "key": "architecture#2", "outcome": "approve"})
}

fn with_args(tool: &str, args: Value) -> CallToolRequestParams {
    CallToolRequestParams::new(tool.to_string())
        .with_arguments(args.as_object().cloned().unwrap_or_default())
}

/// The MRTR retry: same tool and args, the confirm response, and the
/// echoed (or tampered) requestState.
fn confirm_retry(tool: &str, args: Value, state: Option<String>) -> CallToolRequestParams {
    let mut responses = std::collections::BTreeMap::new();
    responses.insert("confirm".to_string(), json!(true));
    let mut params = with_args(tool, args).with_input_responses(responses);
    if let Some(state) = state {
        params = params.with_request_state(state);
    }
    params
}

async fn call_args(
    client: &rmcp::service::RunningService<RoleClient, TestClient>,
    tool: &str,
    args: Value,
) -> CallToolResult {
    tokio::time::timeout(
        Duration::from_secs(15),
        client.call_tool(with_args(tool, args)),
    )
    .await
    .expect("call timed out")
    .expect("call_tool protocol error")
}

async fn call_once_args(
    client: &rmcp::service::RunningService<RoleClient, TestClient>,
    tool: &str,
    args: Value,
) -> CallToolResponse {
    tokio::time::timeout(
        Duration::from_secs(15),
        client.call_tool_once(with_args(tool, args)),
    )
    .await
    .expect("call timed out")
    .expect("call_tool_once protocol error")
}

async fn call_retry(
    client: &rmcp::service::RunningService<RoleClient, TestClient>,
    tool: &str,
    args: Value,
    state: Option<String>,
) -> CallToolResult {
    let response = tokio::time::timeout(
        Duration::from_secs(15),
        client.call_tool_once(confirm_retry(tool, args, state)),
    )
    .await
    .expect("call timed out")
    .expect("retry protocol error");
    match response {
        CallToolResponse::Complete(result) => result,
        other => panic!("retry must complete, got {other:?}"),
    }
}

fn input_required_state(response: CallToolResponse) -> String {
    match response {
        CallToolResponse::InputRequired(result) => {
            result.request_state.expect("input_required carries state")
        }
        other => panic!("expected input_required, got {other:?}"),
    }
}

fn recorded_calls(path: &Path) -> Vec<Value> {
    record_lines(path)
        .into_iter()
        .filter(|r| r["op"] == "call")
        .collect()
}

fn elicited_messages(log: &Arc<Mutex<Vec<ElicitRequestParams>>>) -> Vec<String> {
    log.lock()
        .unwrap()
        .iter()
        .map(|p| match p {
            ElicitRequestParams::FormElicitationParams { message, .. } => message.clone(),
            ElicitRequestParams::UrlElicitationParams { message, .. } => message.clone(),
            _ => String::new(),
        })
        .collect()
}

/// Poll (real time) until the fake bridge records one op — used by the
/// timeout test to freeze the clock only after the preview roundtrip has
/// completed, so no subprocess I/O is pending under paused time.
async fn wait_for_recorded_op(path: &Path, op: &str) {
    for _ in 0..1000 {
        if record_lines(path).iter().any(|r| r["op"] == op) {
            return;
        }
        tokio::time::sleep(Duration::from_millis(10)).await;
    }
    panic!("{op} never reached the bridge");
}

// E1: negotiated protocol < 2026-07-28, elicitation capability present.

#[tokio::test]
async fn confirm_e1_accept_forwards_call_with_expect_digest() {
    let client = TestClient::new_versioned(true, ProtocolVersion::V_2025_11_25);
    let elicited = client.elicited.clone();
    let h = start_cfg("confirm-e1-accept", json!({}), client, None).await;

    let result = call_args(&h.client, "decide_gate", gate_args()).await;
    assert_ne!(result.is_error, Some(true));
    assert_eq!(single_text(&result), "canned result");

    // The elicitation carried the preview's message (FR-006).
    let messages = elicited_messages(&elicited);
    assert_eq!(messages.len(), 1, "exactly one elicitation");
    assert!(messages[0].contains("canned preview"), "{}", messages[0]);

    // The bridge received ONE call, carrying the preview's digest.
    let calls = recorded_calls(&h.record);
    assert_eq!(calls.len(), 1, "exactly one bridge call");
    assert_eq!(calls[0]["tool"], "decide_gate");
    assert_eq!(calls[0]["expect_digest"], "0".repeat(64));
}

#[tokio::test]
async fn confirm_e1_decline_sends_no_call_with_did_not_confirm_sentence() {
    let client = TestClient::new_versioned(true, ProtocolVersion::V_2025_11_25);
    client.set_answer(ElicitAnswer::Decline);
    let h = start_cfg("confirm-e1-decline", json!({}), client, None).await;

    let result = call_args(&h.client, "decide_gate", gate_args()).await;
    assert_eq!(result.is_error, Some(true));
    assert_eq!(single_text(&result), DID_NOT_CONFIRM_SENTENCE);
    assert!(recorded_calls(&h.record).is_empty(), "no call may be sent");
}

#[tokio::test]
async fn confirm_e1_client_cancel_sends_no_call_with_did_not_confirm_sentence() {
    let client = TestClient::new_versioned(true, ProtocolVersion::V_2025_11_25);
    client.set_answer(ElicitAnswer::Abort);
    let h = start_cfg("confirm-e1-cancel", json!({}), client, None).await;

    let result = call_args(&h.client, "decide_gate", gate_args()).await;
    assert_eq!(result.is_error, Some(true));
    assert_eq!(single_text(&result), DID_NOT_CONFIRM_SENTENCE);
    assert!(recorded_calls(&h.record).is_empty(), "no call may be sent");
}

#[tokio::test]
async fn confirm_e1_timeout_sends_no_call_with_did_not_confirm_sentence() {
    let client = TestClient::new_versioned(true, ProtocolVersion::V_2025_11_25);
    client.set_answer(ElicitAnswer::Hang);
    let h = start_cfg("confirm-e1-timeout", json!({}), client, None).await;
    // Complete the handshake in real time first; the clock freezes only
    // once the preview roundtrip is done and the elicitation timer armed.
    let _ = tokio::time::timeout(Duration::from_secs(15), h.client.list_tools(None))
        .await
        .expect("list timed out");

    let Harness { client, record, .. } = h;
    let task = tokio::spawn(async move {
        client
            .call_tool(with_args("decide_gate", gate_args()))
            .await
    });
    wait_for_recorded_op(&record, "preview").await;
    tokio::time::sleep(Duration::from_millis(50)).await; // reply lands, timer arms
    tokio::time::pause();

    let result = tokio::time::timeout(Duration::from_secs(400), task)
        .await
        .expect("the 300 s elicitation timeout must end the call (not 400 s)")
        .expect("join")
        .expect("call_tool protocol error");
    assert_eq!(result.is_error, Some(true));
    assert_eq!(single_text(&result), DID_NOT_CONFIRM_SENTENCE);
    assert!(recorded_calls(&record).is_empty(), "no call may be sent");
}

#[tokio::test]
async fn confirm_e1_without_elicitation_capability_fails_closed() {
    let client = TestClient::new_versioned(false, ProtocolVersion::V_2025_11_25);
    let h = start_cfg("confirm-e1-nocap", json!({}), client, None).await;

    let result = call_args(&h.client, "decide_gate", gate_args()).await;
    assert_eq!(result.is_error, Some(true));
    assert_eq!(single_text(&result), NO_CONFIRMATION_SENTENCE);
    assert!(recorded_calls(&h.record).is_empty(), "no call may be sent");
}

// E2: negotiated protocol >= 2026-07-28 — MRTR input requests, sealed
// requestState, single-use jti, args binding, expiry.

#[tokio::test]
async fn confirm_e2_accept_on_retry_sends_exactly_one_call() {
    let h = start("confirm-e2-accept", json!({})).await;

    // call_tool drives the input_required round itself through the
    // client's elicitation handler (scripted Accept(true)).
    let result = call_args(&h.client, "decide_gate", gate_args()).await;
    assert_ne!(result.is_error, Some(true));
    assert_eq!(single_text(&result), "canned result");

    let calls = recorded_calls(&h.record);
    assert_eq!(calls.len(), 1, "exactly one bridge call");
    assert_eq!(calls[0]["expect_digest"], "0".repeat(64));
}

#[tokio::test]
async fn confirm_e2_tampered_request_state_is_invalid() {
    let h = start("confirm-e2-tampered", json!({})).await;
    let state = input_required_state(call_once_args(&h.client, "decide_gate", gate_args()).await);
    let last = state.chars().last().expect("non-empty state");
    let tampered = format!(
        "{}{}",
        &state[..state.len() - 1],
        if last == 'A' { 'B' } else { 'A' }
    );

    let result = call_retry(&h.client, "decide_gate", gate_args(), Some(tampered)).await;
    assert_eq!(result.is_error, Some(true));
    assert_eq!(single_text(&result), INVALID_SENTENCE);
    assert!(recorded_calls(&h.record).is_empty(), "no call may be sent");
}

#[tokio::test]
async fn confirm_e2_replayed_request_state_is_invalid_and_still_one_call() {
    let h = start("confirm-e2-replay", json!({})).await;
    let state = input_required_state(call_once_args(&h.client, "decide_gate", gate_args()).await);

    let first = call_retry(&h.client, "decide_gate", gate_args(), Some(state.clone())).await;
    assert_ne!(first.is_error, Some(true), "the first use is valid");

    let replay = call_retry(&h.client, "decide_gate", gate_args(), Some(state)).await;
    assert_eq!(replay.is_error, Some(true));
    assert_eq!(single_text(&replay), INVALID_SENTENCE);
    assert_eq!(recorded_calls(&h.record).len(), 1, "still exactly one call");
}

#[tokio::test]
async fn confirm_e2_swapped_args_retry_is_invalid() {
    let h = start("confirm-e2-args-swap", json!({})).await;
    let state = input_required_state(call_once_args(&h.client, "decide_gate", gate_args()).await);
    let swapped =
        json!({"run_id": "feature-add-sso", "key": "architecture#2", "outcome": "reject"});

    let result = call_retry(&h.client, "decide_gate", swapped, Some(state)).await;
    assert_eq!(result.is_error, Some(true));
    assert_eq!(single_text(&result), INVALID_SENTENCE);
    assert!(recorded_calls(&h.record).is_empty(), "no call may be sent");
}

#[tokio::test]
async fn confirm_e2_expired_request_state_is_invalid() {
    // The injected clock ages the state past exp (= issue + 300 s) without
    // sleeping: the offset is bumped between the two rounds.
    let offset = Arc::new(Mutex::new(0u64));
    let bumped = offset.clone();
    let now: Clock = Arc::new(move || {
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_secs()
            + *bumped.lock().unwrap()
    });
    let h = start_cfg(
        "confirm-e2-expired",
        json!({}),
        TestClient::new(true),
        Some(now),
    )
    .await;

    let state = input_required_state(call_once_args(&h.client, "decide_gate", gate_args()).await);
    *offset.lock().unwrap() = 301;
    let result = call_retry(&h.client, "decide_gate", gate_args(), Some(state)).await;

    assert_eq!(result.is_error, Some(true));
    assert_eq!(single_text(&result), INVALID_SENTENCE);
    assert!(recorded_calls(&h.record).is_empty(), "no call may be sent");
}

// Bridge errors on the confirm path surface verbatim (SC-003).

#[tokio::test]
async fn confirm_bridge_changed_error_surfaces_verbatim_as_is_error() {
    let client = TestClient::new_versioned(true, ProtocolVersion::V_2025_11_25);
    let h = start_cfg(
        "confirm-changed",
        json!({"call": [{"frame": {"ok": false, "error": {"code": "changed", "message": "irrelevant — the fixed sentence wins"}}}]}),
        client,
        None,
    )
    .await;

    let result = call_args(&h.client, "decide_gate", gate_args()).await;
    assert_eq!(result.is_error, Some(true));
    assert_eq!(single_text(&result), CHANGED_SENTENCE);
}

#[tokio::test]
async fn confirm_preview_error_is_is_error_and_elicits_nothing() {
    let client = TestClient::new_versioned(true, ProtocolVersion::V_2025_11_25);
    let elicited = client.elicited.clone();
    let sentence = "key 'Q1' on feature-fix-cache takes a text reply; use answer_question";
    let h = start_cfg(
        "confirm-preview-error",
        json!({"preview": [{"frame": {"ok": false, "error": {"code": "tool_error", "message": sentence}}}]}),
        client,
        None,
    )
    .await;

    let result = call_args(&h.client, "decide_gate", gate_args()).await;
    assert_eq!(result.is_error, Some(true));
    assert_eq!(single_text(&result), sentence, "verbatim tool error");
    assert!(
        elicited_messages(&elicited).is_empty(),
        "no human is bothered"
    );
    assert!(recorded_calls(&h.record).is_empty(), "no call may be sent");
}

// ---- the grep test ----------------------------------------------------------

#[test]
fn verb_names_absent() {
    const VERBS: [&str; 12] = [
        "list_runs",
        "get_run",
        "follow",
        "inbox",
        "list_projects",
        "get_project",
        "list_tasks",
        "project_events",
        "read_artifact",
        "start_run",
        "answer_question",
        "decide_gate",
    ];
    let src = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("src");
    // The contract's fixed sentences quote some verb words in prose (the
    // `changed` sentence says "re-read the inbox"); they are verbatim
    // from contracts/bridge-protocol.md and are not tool references.
    let exempt = [
        kroker_mcp::bridge::CHANGED_SENTENCE,
        "the factory raised BridgeDied; the operator should check the server log",
    ];
    let mut checked = 0;
    let mut stack = vec![src];
    while let Some(dir) = stack.pop() {
        for entry in std::fs::read_dir(&dir).unwrap() {
            let entry = entry.unwrap();
            let path = entry.path();
            if path.is_dir() {
                stack.push(path);
                continue;
            }
            if path.extension().and_then(|e| e.to_str()) != Some("rs") {
                continue;
            }
            checked += 1;
            let mut text = std::fs::read_to_string(&path).unwrap();
            for sentence in exempt {
                text = text.replace(sentence, "");
            }
            for verb in VERBS {
                assert!(
                    !text.contains(verb),
                    "{verb} appears in {} — Rust holds zero per-verb logic (research R3)",
                    path.display()
                );
            }
        }
    }
    assert!(
        checked >= 4,
        "expected at least 4 rust sources, saw {checked}"
    );
}
