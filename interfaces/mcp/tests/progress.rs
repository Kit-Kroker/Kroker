//! The progress section (022 T036): bridge-emitted progress frames relayed
//! as notifications/progress to a tokened client, none without a token,
//! and notifications/cancelled forwarded to the bridge as cancel.
//!
//! Split from tests/server.rs along the section seam when that file
//! crossed the 1000-line ceiling; the harness lives in tests/common.

use std::time::Duration;

use serde_json::{Value, json};

use common::{
    TestClient, read_raw, record_lines, send_raw, start_cfg, start_raw, wait_for_recorded_op,
    with_args,
};

mod common;

// ---- section: progress (T036) ----------------------------------------------
//
// Forwarding, not generation: the bridge child emits the frames (the
// scripted fixture writes them verbatim from a step's "lines"); the server
// relays them as notifications/progress to a client that sent a
// progressToken, and relays notifications/cancelled back as a bridge
// cancel. RED until server.rs implements both directions.

/// A call step whose lines are two progress frames for bridge id "b0"
/// followed by the terminal result. Bridge ids are deterministic: the
/// handshake's init does not consume the sequence, so the first call is
/// "b0" (verified against the recorded fixture output).
fn two_progress_then_result() -> Value {
    json!({"call": [{"lines": [
        r#"{"op":"progress","id":"b0","elapsed_s":0.5,"message":"waiting"}"#,
        r#"{"op":"progress","id":"b0","elapsed_s":1.25,"message":"waiting"}"#,
        r#"{"op":"result","id":"b0","ok":true,"value":"done waiting"}"#,
    ]}]})
}

#[tokio::test]
async fn progress_token_receives_both_notifications_in_order() {
    let client = TestClient::new(true);
    let seen = client.progress.clone();
    let h = start_cfg(
        "progress-with-token",
        two_progress_then_result(),
        client,
        None,
    )
    .await;

    // No meta is set by hand: rmcp's client attaches a progress token to
    // every request by itself, which is exactly "a client with a token".
    let result = tokio::time::timeout(
        Duration::from_secs(15),
        h.client.call_tool(with_args("follow", json!({}))),
    )
    .await
    .expect("call timed out")
    .expect("call_tool protocol error");
    assert_ne!(result.is_error, Some(true));

    // Notifications are asynchronous and may land after the response; poll
    // briefly rather than asserting synchronously. The token VALUE is the
    // SDK's own: rmcp's client overwrites any meta token on every outbound
    // request (send_request_with_option_and_subscription →
    // set_progress_token), so we assert consistency, not a chosen value.
    let log = seen.clone();
    let deadline = std::time::Instant::now() + Duration::from_secs(5);
    loop {
        {
            let guard = log.lock().unwrap();
            if guard.len() >= 2 {
                assert_eq!(guard.len(), 2, "exactly the two scripted frames: {guard:?}");
                assert_eq!(guard[0].progress_token, guard[1].progress_token);
                assert_eq!(guard[0].progress, 0.5);
                assert_eq!(guard[0].message.as_deref(), Some("waiting"));
                assert_eq!(guard[1].progress, 1.25);
                break;
            }
        }
        assert!(
            std::time::Instant::now() < deadline,
            "the two progress notifications never arrived"
        );
        tokio::time::sleep(Duration::from_millis(10)).await;
    }
}

#[tokio::test]
async fn progress_without_a_token_sends_no_notifications() {
    // rmcp's own client attaches a numeric progressToken to EVERY request
    // (send_request_with_option_and_subscription → set_progress_token), so
    // "no token" cannot be driven through the SDK client. This drives the
    // transport raw: a tools/call with no _meta at all, and the wire is
    // inspected for what actually comes back.
    let (client_side, _record) = start_raw("progress-no-token", two_progress_then_result()).await;
    let (r, mut w) = tokio::io::split(client_side);
    let mut lines = tokio::io::BufReader::new(r);

    send_raw(
        &mut w,
        json!({"jsonrpc":"2.0","id":1,"method":"initialize","params":{
            "protocolVersion":"2025-11-25",
            "capabilities":{},
            "clientInfo":{"name":"raw-client","version":"0.0.0"}}}),
    )
    .await;
    let init = read_raw(&mut lines).await;
    assert_eq!(init["id"], 1, "the initialize response: {init}");
    send_raw(
        &mut w,
        json!({"jsonrpc":"2.0","method":"notifications/initialized"}),
    )
    .await;
    send_raw(
        &mut w,
        json!({"jsonrpc":"2.0","id":43,"method":"tools/call","params":{
            "name":"follow","arguments":{}}}),
    )
    .await;

    // Read until the id-43 response; NOTHING between it and the
    // initialize response may be a notification.
    let mut seen: Vec<Value> = Vec::new();
    let deadline = std::time::Instant::now() + Duration::from_secs(10);
    loop {
        let frame = tokio::time::timeout_at(deadline.into(), read_raw(&mut lines))
            .await
            .expect("the call must resolve");
        if frame.get("id") == Some(&json!(43)) {
            assert_eq!(frame["result"]["content"][0]["text"], "done waiting");
            break;
        }
        seen.push(frame);
    }
    assert!(seen.is_empty(), "no token, no notifications: {seen:?}");
}

#[tokio::test]
async fn progress_cancel_notification_reaches_the_bridge_as_cancel() {
    // The step never answers the call (no terminal line), so the cancel
    // lands while it is genuinely in flight.
    let scenario = json!({"call": [{"lines": [
        r#"{"op":"progress","id":"b0","elapsed_s":0.1,"message":"waiting"}"#,
    ]}]});
    let (client_side, record) = start_raw("progress-cancel", scenario).await;
    let (r, mut w) = tokio::io::split(client_side);
    let mut lines = tokio::io::BufReader::new(r);

    send_raw(
        &mut w,
        json!({"jsonrpc":"2.0","id":1,"method":"initialize","params":{
            "protocolVersion":"2025-11-25",
            "capabilities":{},
            "clientInfo":{"name":"raw-client","version":"0.0.0"}}}),
    )
    .await;
    let init = read_raw(&mut lines).await;
    assert_eq!(init["id"], 1, "the initialize response: {init}");
    send_raw(
        &mut w,
        json!({"jsonrpc":"2.0","method":"notifications/initialized"}),
    )
    .await;
    send_raw(
        &mut w,
        json!({"jsonrpc":"2.0","id":42,"method":"tools/call","params":{
            "name":"follow","arguments":{}}}),
    )
    .await;
    // Drain the scripted progress notification so the pipe never blocks.
    let _progress = tokio::time::timeout(Duration::from_secs(5), read_raw(&mut lines)).await;
    wait_for_recorded_op(&record, "call").await;

    send_raw(
        &mut w,
        json!({"jsonrpc":"2.0","method":"notifications/cancelled","params":{"requestId":42}}),
    )
    .await;

    // The server maps MCP request id 42 to its bridge id for that call
    // ("b0": the first call of the session) and forwards the cancel.
    let deadline = std::time::Instant::now() + Duration::from_secs(10);
    loop {
        let records = record_lines(&record);
        let cancelled: Vec<&Value> = records.iter().filter(|r| r["op"] == "cancel").collect();
        if !cancelled.is_empty() {
            assert_eq!(cancelled[0]["id"], "b0", "the bridge id of the call");
            return;
        }
        assert!(
            std::time::Instant::now() < deadline,
            "cancel never reached the bridge"
        );
        tokio::time::sleep(Duration::from_millis(10)).await;
    }
}
