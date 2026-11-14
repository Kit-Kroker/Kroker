//! The write-confirmation gate (022 T029, contracts/mcp-tools.md §Write
//! confirmation, research R4).
//!
//! Every confirm tool funnels through [`confirm_and_call`]: preview the
//! write, obtain a human's boolean, and only then send the bridge a call
//! carrying the preview's digest (FR-005 — there is no unconfirmed path,
//! ever). Which elicitation mechanism is used is purely a function of the
//! negotiated protocol revision and the client's capabilities:
//!
//! - **E1** (< 2026-07-28): `elicitation/create` with the confirmation
//!   form, 300 s timeout.
//! - **E2** (>= 2026-07-28): an MRTR `input_required` round; the state is
//!   an HMAC-sealed [`SealedState`] (single-use jti, bound to the tool,
//!   the args hash and the digest, expiring after 300 s).
//! - **None**: the session cannot elicit — the write fails closed.
//!
//! Zero per-verb logic: the caller hands over a descriptor-derived name;
//! no verb name appears here (research R3, the grep test).

use std::collections::BTreeMap;
use std::sync::Arc;
use std::time::Duration;

use rmcp::ErrorData as McpError;
use rmcp::elicit_safe;
use rmcp::model::{
    CallToolResponse, ElicitRequest, ElicitRequestParams, ElicitResult, ElicitationAction,
    ElicitationSchema, InputRequest, InputRequiredResult, InputResponses, RequestStateCodec,
};
use rmcp::service::{Peer, RoleServer};
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use sha2::{Digest, Sha256};
use tokio::sync::Mutex;

use crate::bridge::Bridge;
use crate::server::{ElicitMode, NO_CONFIRMATION_SENTENCE, map_error, map_result};

/// Decline, cancel, timeout or `confirm=false` (contracts/mcp-tools.md).
pub const DID_NOT_CONFIRM_SENTENCE: &str = "the operator did not confirm; nothing was changed";

/// Bad, expired, replayed or mismatched requestState (contracts/mcp-tools.md).
pub const INVALID_SENTENCE: &str =
    "this confirmation is invalid or was already used; nothing was changed — call the tool again";

/// E1's elicitation window and the E2 state TTL (contracts/mcp-tools.md).
const CONFIRM_WINDOW: Duration = Duration::from_secs(300);

/// The bounded replay table's capacity (data-model.md `consumed_jti`):
/// 1024 live entries; a table that is full after sweeping fails closed.
const MAX_CONSUMED_JTI: usize = 1024;

/// The confirmation form: one boolean and no default — an absent
/// `confirm` is a schema failure and fails closed.
#[derive(Serialize, Deserialize, JsonSchema)]
struct Confirm {
    confirm: bool,
}

elicit_safe!(Confirm);

/// The E2 requestState payload (data-model.md SealedState), HMAC-sealed
/// by [`RequestStateCodec`]. `exp` is unix seconds.
#[derive(Serialize, Deserialize)]
struct SealedState {
    jti: String,
    tool: String,
    args_sha256: String,
    digest: String,
    exp: u64,
}

/// Test seam for the unix-seconds clock (None = the system clock).
pub type Now = Arc<dyn Fn() -> u64 + Send + Sync>;

/// Per-session confirmation state: the sealing key (getrandom at
/// startup) and the bounded single-use jti table.
pub struct ConfirmGate {
    codec: RequestStateCodec,
    consumed: Mutex<BTreeMap<String, u64>>,
    now: Option<Now>,
}

impl ConfirmGate {
    pub fn new(now: Option<Now>) -> Self {
        let mut key = [0u8; 32];
        getrandom::fill(&mut key).expect("the OS CSPRNG cannot fail here");
        // try_new only rejects keys shorter than the minimum signing
        // length; 32 random bytes always qualify, so the Err arm is
        // unreachable by construction.
        let codec =
            RequestStateCodec::try_new(key.to_vec()).expect("a 32-byte key is always accepted");
        Self {
            codec,
            consumed: Mutex::new(BTreeMap::new()),
            now,
        }
    }

    fn now(&self) -> u64 {
        self.now.as_ref().map_or_else(system_now, |f| f())
    }

    /// Seal a fresh state for `tool`/`args` at `digest`, expiring in 300 s.
    fn seal(&self, tool: &str, args: &Value, digest: &str) -> Result<String, McpError> {
        let state = SealedState {
            jti: uuid::Uuid::new_v4().to_string(),
            tool: tool.to_string(),
            args_sha256: args_sha256(args),
            digest: digest.to_string(),
            exp: self.now() + CONFIRM_WINDOW.as_secs(),
        };
        self.codec
            .seal_json(&state)
            .map_err(|_| McpError::internal_error("could not seal the confirmation state", None))
    }

    /// Open and validate a retried state, then mark its jti consumed.
    /// Every failure — tampered, wrong tool, swapped args, expired,
    /// replayed jti, or a replay table full of live entries — is the
    /// same invalid-confirmation outcome: fail closed, reveal nothing.
    async fn consume(&self, sealed: &str, tool: &str, args: &Value) -> Result<String, ()> {
        let state: SealedState = self.codec.open_json(sealed).map_err(|_| ())?;
        let now = self.now();
        if state.tool != tool || state.args_sha256 != args_sha256(args) || now >= state.exp {
            return Err(());
        }
        let mut consumed = self.consumed.lock().await;
        if consumed.contains_key(&state.jti) {
            return Err(());
        }
        consumed.retain(|_, exp| *exp > now); // sweep entries past their exp
        if consumed.len() >= MAX_CONSUMED_JTI {
            return Err(());
        }
        consumed.insert(state.jti.clone(), state.exp);
        Ok(state.digest)
    }
}

fn system_now() -> u64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or(0)
}

/// sha256 hex of the args' canonical JSON. serde_json without
/// `preserve_order` keeps every object a BTreeMap, so `to_string` emits
/// keys sorted at every depth — those are the canonical bytes.
fn args_sha256(args: &Value) -> String {
    let bytes = serde_json::to_string(args).unwrap_or_default();
    to_hex(&Sha256::digest(bytes.as_bytes()))
}

fn to_hex(bytes: &[u8]) -> String {
    bytes.iter().map(|b| format!("{b:02x}")).collect()
}

/// What one confirmed call needs, handed over by server.rs. `bridge_id`
/// is the call's bridge id — server.rs pre-allocated it so a client
/// cancellation can be forwarded while the write is in flight (T036).
pub struct ConfirmSession<'a> {
    pub gate: &'a Arc<ConfirmGate>,
    pub bridge: &'a Arc<Bridge>,
    pub mode: ElicitMode,
    pub peer: &'a Peer<RoleServer>,
    pub bridge_id: String,
}

/// The whole write-confirmation flow (T029). Returns the client-facing
/// response: an input_required round, an isError sentence, or the
/// bridge's mapped result.
pub async fn confirm_and_call(
    session: &ConfirmSession<'_>,
    tool: &str,
    args: &Value,
    request_state: Option<&str>,
    input_responses: Option<&InputResponses>,
) -> Result<CallToolResponse, McpError> {
    // 0. An E2 retry validates (and burns) its sealed state BEFORE any
    //    bridge I/O. Preview-first is unreachable-correct on this path:
    //    the state's own first use resolved the pending item it sealed,
    //    so a replay's preview would fail NoMatch and mask the
    //    contract's invalid-confirmation sentence (mcp-tools.md refusal
    //    table outranks the sketch's ordering; found by the T030 replay
    //    parity test). Bonus: a tampered/expired/replayed state now
    //    costs zero bridge roundtrips.
    let sealed_digest = match (session.mode, request_state) {
        (ElicitMode::E2, Some(sealed)) => match session.gate.consume(sealed, tool, args).await {
            Ok(digest) => Some(digest),
            Err(()) => return Ok(error_result(INVALID_SENTENCE)),
        },
        _ => None,
    };

    // 1. Preview. An error here is the operator's to read — no human is
    //    bothered with a write that cannot even be described (SC-003).
    //    On an E2 retry with a still-valid state this may honestly fail
    //    (another channel resolved the item in between); that surfaces
    //    verbatim, which is the truthful answer.
    let preview_id = session.bridge.next_id();
    let preview = match session.bridge.preview(&preview_id, tool, args).await {
        Ok(preview) => preview,
        Err(e) => return Ok(map_error(e).into()),
    };

    match session.mode {
        ElicitMode::None => Ok(error_result(NO_CONFIRMATION_SENTENCE)),
        ElicitMode::E1 => {
            // Decline, cancel, timeout, a schema failure or confirm=false
            // all land on the same sentence: nothing was changed.
            let answer = session
                .peer
                .elicit_with_timeout::<Confirm>(preview.message.clone(), Some(CONFIRM_WINDOW))
                .await;
            match answer {
                Ok(Some(form)) if form.confirm => {
                    call_confirmed(session, tool, args, &preview.digest).await
                }
                _ => Ok(error_result(DID_NOT_CONFIRM_SENTENCE)),
            }
        }
        ElicitMode::E2 => {
            let Some(digest) = sealed_digest else {
                // First round: issue the same confirmation form as an
                // input request, with the sealed state to echo back.
                let sealed = session.gate.seal(tool, args, &preview.digest)?;
                let schema = ElicitationSchema::from_type::<Confirm>().map_err(|_| {
                    McpError::internal_error("could not build the confirmation form", None)
                })?;
                let mut requests = BTreeMap::new();
                requests.insert(
                    "confirm".to_string(),
                    InputRequest::Elicitation(ElicitRequest::new(
                        ElicitRequestParams::FormElicitationParams {
                            meta: None,
                            message: preview.message,
                            requested_schema: schema,
                        },
                    )),
                );
                return Ok(CallToolResponse::InputRequired(InputRequiredResult::new(
                    Some(requests),
                    Some(sealed),
                )));
            };
            // Retry with a valid state: the digest the human approved is
            // the sealed one — if the world moved since, the bridge's
            // own digest check answers `changed` (FR-006).
            if !response_confirms(input_responses.and_then(|r| r.get("confirm"))) {
                return Ok(error_result(DID_NOT_CONFIRM_SENTENCE));
            }
            call_confirmed(session, tool, args, &digest).await
        }
    }
}

/// The confirmed write: exactly one bridge call, carrying the digest the
/// human approved. The bridge re-checks it against a freshly computed
/// preview and answers `changed` if the world moved (FR-006).
async fn call_confirmed(
    session: &ConfirmSession<'_>,
    tool: &str,
    args: &Value,
    digest: &str,
) -> Result<CallToolResponse, McpError> {
    let bridge = session.bridge;
    Ok(match bridge
        .call(&session.bridge_id, tool, args, Some(digest))
        .await
    {
        Ok(value) => map_result(value),
        Err(e) => map_error(e),
    }
    .into())
}

/// Did the client's `input_responses["confirm"]` carry a human's yes?
/// Spec-shaped clients send the serialized [`ElicitResult`]; a
/// hand-rolled client may send the bare form value. Anything else —
/// absent, malformed, declined, or `confirm: false` — is a no.
fn response_confirms(value: Option<&Value>) -> bool {
    let Some(value) = value else {
        return false;
    };
    if let Ok(result) = serde_json::from_value::<ElicitResult>(value.clone()) {
        return result.action == ElicitationAction::Accept
            && result
                .content
                .as_ref()
                .and_then(|c| c.get("confirm"))
                .and_then(Value::as_bool)
                == Some(true);
    }
    value.as_bool() == Some(true)
}

fn error_result(sentence: &str) -> CallToolResponse {
    rmcp::model::CallToolResult::error(vec![rmcp::model::ContentBlock::text(sentence.to_string())])
        .into()
}
