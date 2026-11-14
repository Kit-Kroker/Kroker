//! The write-confirmation gate (022, contracts/mcp-tools.md §Write
//! confirmation, research R4).
//!
//! STUB (T028): every confirm tool fails closed with the no-confirmation
//! sentence and never reaches the bridge, so the test section's accept,
//! E2 and replay cases fail for the expected reason (no `call` is sent)
//! while the fail-closed cases already pass. T029 replaces the body with
//! the E1/E2 elicitation handshake.

use rmcp::model::{CallToolResponse, CallToolResult, ContentBlock};

use crate::server::NO_CONFIRMATION_SENTENCE;

/// Decline, cancel, timeout or `confirm=false` (contracts/mcp-tools.md).
pub const DID_NOT_CONFIRM_SENTENCE: &str = "the operator did not confirm; nothing was changed";

/// Bad, expired, replayed or mismatched requestState (contracts/mcp-tools.md).
pub const INVALID_SENTENCE: &str =
    "this confirmation is invalid or was already used; nothing was changed — call the tool again";

/// Route every confirm tool through this gate; server.rs branches only on
/// the descriptor's `confirm` metadata (research R3). The signature grows
/// what the real handshake needs when T029 lands.
pub async fn confirm_and_call() -> Result<CallToolResponse, rmcp::ErrorData> {
    Ok(CallToolResult::error(vec![ContentBlock::text(
        NO_CONFIRMATION_SENTENCE.to_string(),
    )])
    .into())
}
