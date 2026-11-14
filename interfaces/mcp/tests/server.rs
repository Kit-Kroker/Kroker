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
    CallToolRequestParams, CallToolResult, ClientConfig, ContentBlock, ElicitRequestParams,
    ElicitResult, ElicitationAction, ElicitationCapability, FormElicitationCapability,
    Implementation, ProgressNotificationParam, ProtocolVersion,
};
use rmcp::service::NotificationContext;
use rmcp::service::{RequestContext, RoleClient};
use rmcp::{ClientHandler, ErrorData as McpError, ServiceExt};
use serde_json::{Value, json};

use kroker_mcp::server::{Server, ServerConfig};

static DIR_SEQ: AtomicUsize = AtomicUsize::new(0);

// ---- the scripted client -------------------------------------------------

/// What the client answers when the server elicits.
/// (T028's confirm tests script every variant; until then the linter
/// would flag the unused ones.)
#[allow(dead_code)]
#[derive(Clone, Debug, PartialEq)]
enum ElicitAnswer {
    /// accept, carrying `confirm`.
    Accept(bool),
    Decline,
    /// The request dies (as a client-side cancel would).
    Abort,
}

#[derive(Clone)]
struct TestClient {
    elicitation: bool,
    answer: Arc<Mutex<ElicitAnswer>>,
    elicited: Arc<Mutex<Vec<ElicitRequestParams>>>,
    progress: Arc<Mutex<Vec<ProgressNotificationParam>>>,
    cancelled: Arc<Mutex<Vec<Value>>>,
}

impl TestClient {
    fn new(elicitation: bool) -> Self {
        Self {
            elicitation,
            answer: Arc::new(Mutex::new(ElicitAnswer::Accept(true))),
            elicited: Arc::new(Mutex::new(Vec::new())),
            progress: Arc::new(Mutex::new(Vec::new())),
            cancelled: Arc::new(Mutex::new(Vec::new())),
        }
    }

    #[allow(dead_code)] // T028 scripts decline/abort
    fn set_answer(&self, answer: ElicitAnswer) {
        *self.answer.lock().unwrap() = answer;
    }
}

impl ClientHandler for TestClient {
    fn get_info(&self) -> ClientConfig {
        let mut info = ClientConfig::default();
        info.client_info = Implementation::new("parity-client", "0.0.0");
        info.protocol_version = ProtocolVersion::LATEST;
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
        match self.answer.lock().unwrap().clone() {
            ElicitAnswer::Accept(confirm) => Ok(ElicitResult::new(ElicitationAction::Accept)
                .with_content(json!({ "confirm": confirm }))),
            ElicitAnswer::Decline => Ok(ElicitResult::new(ElicitationAction::Decline)),
            ElicitAnswer::Abort => Err(McpError::new(
                rmcp::model::ErrorCode::INTERNAL_ERROR,
                "elicitation aborted by test client",
                None,
            )),
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

async fn start(name: &str, mut scenario: Value) -> Harness {
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
    };

    let (server_side, client_side) = tokio::io::duplex(64 * 1024);
    let server = tokio::spawn(async move {
        let svc = Server::new(cfg).serve(server_side).await.expect("serve");
        svc.waiting().await.expect("wait");
    });
    let client = TestClient::new(true)
        .serve(client_side)
        .await
        .expect("client");
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
