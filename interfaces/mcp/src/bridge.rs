//! Bridge types shared by the server and the supervisor (022).
//!
//! Stub phase (T017): the surface compiles, every body is `todo!()`.
//! T018 replaces this file with the child supervisor and protocol
//! client per contracts/bridge-protocol.md §Rust-side obligations.

use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::path::PathBuf;

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
    /// The fixed `internal` sentence used when the child dies or a frame
    /// is oversize/unparsable (bridge-protocol.md; the type token is
    /// stable so clients never see a raw OS error).
    pub fn child_died() -> Self {
        BridgeError::Internal(internal_sentence())
    }
}

pub fn internal_sentence() -> String {
    "the factory raised BridgeDied; the operator should check the server log".to_string()
}

/// The supervised Python child: one per MCP session.
pub struct Bridge {
    #[allow(dead_code)]
    repo: PathBuf,
    #[allow(dead_code)]
    bridge_cmd: Option<Vec<String>>,
}

impl Bridge {
    /// Spawn the bridge child and complete the init/describe handshake.
    /// `bridge_cmd` overrides the default
    /// `<repo>/.venv/bin/python -m sdlc.operator.bridge` (tests).
    pub async fn spawn(
        _repo: PathBuf,
        _bridge_cmd: Option<Vec<String>>,
        _actor: &str,
    ) -> Result<(Bridge, Vec<ToolDescriptor>), String> {
        todo!("T018: spawn + init/describe handshake (20 s timeout)")
    }

    /// A pure-read preview for a confirm tool.
    pub async fn preview(
        &self,
        id: &str,
        tool: &str,
        args: &Value,
    ) -> Result<PreviewResult, BridgeError> {
        let _ = (id, tool, args);
        todo!("T018")
    }

    /// Run one tool call; `expect_digest` is required for confirm tools.
    pub async fn call(
        &self,
        id: &str,
        tool: &str,
        args: &Value,
        expect_digest: Option<&str>,
    ) -> Result<Value, BridgeError> {
        let _ = (id, tool, args, expect_digest);
        todo!("T018")
    }

    /// Cancel an in-flight request by bridge id.
    pub async fn cancel(&self, id: &str) {
        let _ = id;
        todo!("T018")
    }
}
