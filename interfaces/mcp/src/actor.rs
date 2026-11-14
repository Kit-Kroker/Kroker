//! Actor identity for the MCP surface (FR-007, research R8).
//!
//! The actor is self-asserted, exactly like `chat:local` and the
//! dashboard's `X-Actor`: it reaches `GateDecision.reviewer` only, never
//! `decided_by`, and the bridge re-validates the regex on `init`.

/// Normalise an MCP clientInfo.name into an actor string.
///
/// lowercase; every run of characters outside `[a-z0-9]` collapses to one
/// `-`; leading/trailing `-` stripped; truncated to 40; empty becomes
/// `mcp:local`. Unsafe names (spaces, control characters, `../../admin`,
/// 500 chars) are neutralised before they reach any audit trail.
pub fn normalise(name: &str) -> String {
    let mut out = String::with_capacity(name.len());
    let mut prev_dash = false;
    for ch in name.chars() {
        let c = if ch.is_ascii() {
            ch.to_ascii_lowercase()
        } else {
            ch
        };
        if c.is_ascii_lowercase() || c.is_ascii_digit() {
            out.push(c);
            prev_dash = false;
        } else if !prev_dash {
            out.push('-');
            prev_dash = true;
        }
    }
    let trimmed = out.trim_matches('-');
    let mut segment = String::with_capacity(trimmed.len());
    for (i, c) in trimmed.chars().enumerate() {
        if i >= 40 {
            break;
        }
        segment.push(c);
    }
    if segment.is_empty() {
        "mcp:local".to_string()
    } else {
        format!("mcp:{segment}")
    }
}

/// Validate an SDLC_MCP_ACTOR override against ^mcp:[a-z0-9-]{1,40}$.
///
/// Ok(actor) on success; Err(message) names the rule (stderr + exit 2 in
/// main). The value itself is echoed back only to the operator's own
/// stderr, never into any frame.
pub fn validate_override(value: &str) -> Result<String, String> {
    let invalid =
        || format!("invalid SDLC_MCP_ACTOR {value:?}: must match ^mcp:[a-z0-9-]{{1,40}}$");
    let rest = value.strip_prefix("mcp:").ok_or_else(invalid)?;
    let len = rest.chars().count();
    if !(1..=40).contains(&len) {
        return Err(invalid());
    }
    if !rest
        .chars()
        .all(|c| c.is_ascii_lowercase() || c.is_ascii_digit() || c == '-')
    {
        return Err(invalid());
    }
    Ok(value.to_string())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn spaces_collapse_to_one_dash() {
        assert_eq!(normalise("Claude Code"), "mcp:claude-code");
    }

    #[test]
    fn trailing_punct_is_stripped() {
        assert_eq!(normalise("Claude Code!!!"), "mcp:claude-code");
    }

    #[test]
    fn path_tricks_cannot_escape_the_prefix() {
        assert_eq!(normalise("../../admin"), "mcp:admin");
    }

    #[test]
    fn control_characters_are_stripped() {
        assert_eq!(normalise("bad\u{1}\u{2}name"), "mcp:bad-name");
        assert_eq!(normalise("a\u{7f}b"), "mcp:a-b");
    }

    #[test]
    fn a_500_char_name_truncates_to_40_after_the_prefix() {
        let actor = normalise(&"c".repeat(500));
        assert_eq!(actor.len(), "mcp:".len() + 40);
        assert_eq!(actor, format!("mcp:{}", "c".repeat(40)));
    }

    #[test]
    fn empty_or_all_punct_becomes_local() {
        assert_eq!(normalise(""), "mcp:local");
        assert_eq!(normalise("!!!"), "mcp:local");
    }

    #[test]
    fn override_accepts_a_valid_actor() {
        assert_eq!(validate_override("mcp:ok-1").as_deref(), Ok("mcp:ok-1"));
    }

    #[test]
    fn override_rejects_wrong_prefix_and_case() {
        assert!(validate_override("chat:x").is_err());
        assert!(validate_override("mcp:Bad").is_err());
    }
}
