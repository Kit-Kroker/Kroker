//! The MCP server surface (022): a metadata-driven `ServerHandler` that
//! serves whatever the Python bridge's `describe` publishes.
//!
//! Stub phase (T017): compiles, serves no tools — `list_tools` and
//! `call_tool` are `todo!()` so the integration tests fail at runtime
//! for the expected reason. T019 implements the reads and the result
//! mapping; confirm tools route to `confirm.rs` from T028/T029.

use std::path::PathBuf;
use std::sync::Arc;

use rmcp::model::{
    CallToolRequestParams, CallToolResponse, InitializeResult, ListToolsResult,
    PaginatedRequestParams, ServerCapabilities,
};
use rmcp::service::{RequestContext, RoleServer};
use rmcp::{ErrorData as McpError, ServerHandler};

use crate::bridge::Bridge;

/// How the binary was launched (main.rs parses; tests construct directly).
#[derive(Debug, Clone)]
pub struct ServerConfig {
    /// The repo root: the bridge child's cwd and the `.venv` home.
    pub repo: PathBuf,
    /// Test override for the bridge argv (`--bridge-cmd`).
    pub bridge_cmd: Option<Vec<String>>,
    /// Validated `SDLC_MCP_ACTOR` override.
    pub actor_override: Option<String>,
}

/// Per-session state, populated during the initialize handshake.
pub struct SessionState {
    /// The supervised bridge child, spawned on `initialized`.
    pub bridge: Option<Arc<Bridge>>,
}

pub struct Server {
    #[allow(dead_code)]
    pub(crate) cfg: ServerConfig,
    pub(crate) state: Arc<std::sync::Mutex<SessionState>>,
}

impl Server {
    pub fn new(cfg: ServerConfig) -> Self {
        Self {
            cfg,
            state: Arc::new(std::sync::Mutex::new(SessionState { bridge: None })),
        }
    }
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

    fn list_tools(
        &self,
        request: Option<PaginatedRequestParams>,
        context: RequestContext<RoleServer>,
    ) -> impl Future<Output = Result<ListToolsResult, McpError>> + Send + '_ {
        let _ = (request, context);
        async { todo!("T019: map describe to rmcp Tool list") }
    }

    fn call_tool(
        &self,
        request: CallToolRequestParams,
        context: RequestContext<RoleServer>,
    ) -> impl Future<Output = Result<CallToolResponse, McpError>> + Send + '_ {
        let _ = (request, context);
        async { todo!("T019: bridge call -> result mapping") }
    }
}
