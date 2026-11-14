//! The MCP server surface (022 T019): a metadata-driven `ServerHandler`
//! that serves whatever the Python bridge's `describe` publishes.
//!
//! Zero per-verb logic: `list_tools` maps descriptors to
//! `rmcp::model::Tool` with annotation hints, and `call_tool` branches
//! only on the descriptor's `confirm` flag (research R3; the grep test
//! enforces it). Confirm tools fail closed until `confirm.rs` lands
//! (T028/T029): FR-005, no unconfirmed path, ever.

use std::path::PathBuf;
use std::sync::Arc;
use std::time::Duration;

use rmcp::model::{
    CallToolRequestParams, CallToolResponse, CallToolResult, ClientCapabilities, ContentBlock,
    InitializeResult, ListToolsResult, PaginatedRequestParams, ServerCapabilities, Tool,
    ToolAnnotations,
};
use rmcp::service::{NotificationContext, RequestContext, RoleServer};
use rmcp::{ErrorData as McpError, ServerHandler};
use serde_json::Value;
use tokio::sync::{Mutex, oneshot};
use tracing::warn;

use crate::actor;
use crate::bridge::{Bridge, BridgeError, ToolDescriptor};

/// The protocol revision where server-to-client elicitation became MRTR
/// input requests (research R1): below it E1 (`elicitation/create`),
/// at or above it E2 (`InputRequiredResult`).
pub const MRTR_PROTOCOL_VERSION: &str = "2026-07-28";

/// FR-005 fail-closed sentence (contracts/mcp-tools.md), used until the
/// confirmation machinery lands and whenever a session cannot elicit.
pub const NO_CONFIRMATION_SENTENCE: &str = "this write needs a human confirmation that this MCP client did not provide; nothing was changed. Use the dashboard or `python -m sdlc.cli` instead.";

/// How this binary was launched (main.rs parses; tests construct directly).
#[derive(Debug, Clone)]
pub struct ServerConfig {
    /// The repo root: the bridge child's cwd and the `.venv` home.
    pub repo: PathBuf,
    /// Test override for the bridge argv (`--bridge-cmd`).
    pub bridge_cmd: Option<Vec<String>>,
    /// Validated `SDLC_MCP_ACTOR` override.
    pub actor_override: Option<String>,
}

/// Which elicitation path this session negotiated (data-model.md).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ElicitMode {
    /// < 2026-07-28 with elicitation capability: `elicitation/create`.
    E1,
    /// >= 2026-07-28 with elicitation capability: MRTR input requests.
    E2,
    /// No path: writes fail closed in this session.
    None,
}

/// Per-session state, populated during the initialize handshake.
pub struct SessionState {
    pub bridge: Option<Arc<Bridge>>,
    pub tools: Option<Arc<Vec<ToolDescriptor>>>,
    pub protocol_version: Option<String>,
    pub elicit_mode: ElicitMode,
    tools_rx: Option<oneshot::Receiver<Arc<Vec<ToolDescriptor>>>>,
}

pub struct Server {
    pub(crate) cfg: ServerConfig,
    pub(crate) state: Arc<Mutex<SessionState>>,
}

impl Server {
    pub fn new(cfg: ServerConfig) -> Self {
        Self {
            cfg,
            state: Arc::new(Mutex::new(SessionState {
                bridge: None,
                tools: None,
                protocol_version: None,
                elicit_mode: ElicitMode::None,
                tools_rx: None,
            })),
        }
    }

    fn elicit_mode(version: &str, caps: &ClientCapabilities) -> ElicitMode {
        let Some(elicitation) = caps.elicitation.as_ref() else {
            return ElicitMode::None;
        };
        if elicitation.form.is_none() && elicitation.url.is_none() {
            return ElicitMode::None;
        }
        if version >= MRTR_PROTOCOL_VERSION {
            ElicitMode::E2
        } else {
            ElicitMode::E1
        }
    }

    /// The session's tools, awaiting the bridge handshake (20 s).
    async fn tools(&self) -> Result<Arc<Vec<ToolDescriptor>>, McpError> {
        let cached = self.state.lock().await.tools.clone();
        if let Some(tools) = cached {
            return Ok(tools);
        }
        let rx = self.state.lock().await.tools_rx.take();
        let Some(rx) = rx else {
            return Err(McpError::internal_error(
                "the bridge session is not initialised",
                None,
            ));
        };
        let tools = tokio::time::timeout(Duration::from_secs(20), rx)
            .await
            .map_err(|_| {
                McpError::internal_error("the bridge did not describe its tools in 20 s", None)
            })?
            .map_err(|_| McpError::internal_error("the bridge handshake failed", None))?;
        self.state.lock().await.tools = Some(tools.clone());
        Ok(tools)
    }

    /// The session's bridge, once `initialized` has spawned it.
    pub(crate) async fn bridge(&self) -> Result<Arc<Bridge>, McpError> {
        self.tools().await?; // ensures the handshake completed first
        self.state
            .lock()
            .await
            .bridge
            .clone()
            .ok_or_else(|| McpError::internal_error("the bridge session is not initialised", None))
    }
}

fn descriptor_to_tool(d: &ToolDescriptor) -> Tool {
    let schema: serde_json::Map<String, Value> =
        d.input_schema.as_object().cloned().unwrap_or_default();
    let mut tool = Tool::new(d.name.clone(), d.description.clone(), schema);
    if let Some(out) = &d.output_schema {
        tool.output_schema = Some(Arc::new(out.as_object().cloned().unwrap_or_default()));
    }
    let mut annotations = ToolAnnotations::default()
        .read_only(d.read_only)
        .open_world(false);
    if !d.read_only {
        annotations = annotations.destructive(true).idempotent(false);
    }
    tool.annotations = Some(annotations);
    tool
}

/// Map a bridge result value per contracts/mcp-tools.md §Result rules:
/// text -> one text block; object -> structuredContent plus the same
/// JSON as text (for clients without structured-content support).
pub(crate) fn map_result(value: Value) -> CallToolResult {
    if value.is_string() {
        let text = value.as_str().unwrap_or_default().to_string();
        CallToolResult::success(vec![ContentBlock::text(text)])
    } else {
        CallToolResult::structured(value)
    }
}

/// Map a bridge error per contracts/mcp-tools.md: `isError: true` and the
/// message verbatim — nothing else may reach the client (SC-003).
pub(crate) fn map_error(error: BridgeError) -> CallToolResult {
    CallToolResult::error(vec![ContentBlock::text(error.message())])
}

impl ServerHandler for Server {
    fn get_info(&self) -> InitializeResult {
        // Tools capability ONLY (contracts/mcp-tools.md): no resources,
        // prompts, sampling or logging.
        let mut info = InitializeResult::new(ServerCapabilities::builder().enable_tools().build());
        info.server_info =
            rmcp::model::Implementation::new("kroker-mcp", env!("CARGO_PKG_VERSION"));
        info
    }

    async fn initialize(
        &self,
        request: rmcp::model::InitializeRequestParams,
        _context: RequestContext<RoleServer>,
    ) -> Result<InitializeResult, McpError> {
        let negotiated = self.negotiate_initialize(&request)?;
        let version = negotiated.protocol_version.to_string();
        let mode = Self::elicit_mode(&version, &request.capabilities);
        let mut state = self.state.lock().await;
        state.protocol_version = Some(version);
        state.elicit_mode = mode;
        Ok(negotiated)
    }

    async fn on_initialized(&self, _context: NotificationContext<RoleServer>) {
        let actor = self
            .cfg
            .actor_override
            .clone()
            .or_else(|| {
                _context
                    .peer
                    .peer_info()
                    .map(|info| actor::normalise(&info.client_info.name))
            })
            .unwrap_or_else(|| "mcp:local".to_string());
        let (tx, rx) = oneshot::channel();
        self.state.lock().await.tools_rx = Some(rx);
        let repo = self.cfg.repo.clone();
        let bridge_cmd = self.cfg.bridge_cmd.clone();
        let state = self.state.clone();
        tokio::spawn(async move {
            match Bridge::spawn(repo, bridge_cmd, &actor).await {
                Ok((bridge, tools)) => {
                    let tools = Arc::new(tools);
                    let bridge = Arc::new(bridge);
                    {
                        let mut s = state.lock().await;
                        s.bridge = Some(bridge.clone());
                        s.tools = Some(tools.clone());
                    }
                    let _ = tx.send(tools);
                }
                Err(e) => {
                    warn!("bridge spawn failed: {e}");
                    // leave tools_rx unsatisfied: callers time out with a
                    // fixed sentence instead of a raw error (SC-003).
                }
            }
        });
    }

    async fn list_tools(
        &self,
        _request: Option<PaginatedRequestParams>,
        _context: RequestContext<RoleServer>,
    ) -> Result<ListToolsResult, McpError> {
        let tools = self.tools().await?;
        Ok(ListToolsResult {
            tools: tools.iter().map(descriptor_to_tool).collect(),
            next_cursor: None,
            ..Default::default()
        })
    }

    async fn call_tool(
        &self,
        request: CallToolRequestParams,
        _context: RequestContext<RoleServer>,
    ) -> Result<CallToolResponse, McpError> {
        let tools = self.tools().await?;
        let Some(descriptor) = tools.iter().find(|d| d.name == request.name) else {
            return Ok(CallToolResult::error(vec![ContentBlock::text(format!(
                "unknown tool '{}'",
                request.name
            ))])
            .into());
        };
        let args = Value::Object(request.arguments.clone().unwrap_or_default());
        let bridge = self.bridge().await?;
        if descriptor.confirm != "none" {
            // T028/T029 route this through confirm_and_call; until then
            // and in any session without an elicitation path, fail closed.
            return Ok(CallToolResult::error(vec![ContentBlock::text(
                NO_CONFIRMATION_SENTENCE.to_string(),
            )])
            .into());
        }
        let id = bridge.next_id();
        let result = bridge.call(&id, &descriptor.name, &args, None).await;
        Ok(match result {
            Ok(value) => map_result(value),
            Err(e) => map_error(e),
        }
        .into())
    }
}
