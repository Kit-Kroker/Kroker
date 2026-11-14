//! kroker-mcp binary entry (022 T019, plan T031).
//!
//! Usage: kroker-mcp --repo <path> [--bridge-cmd <argv…>]
//! Env: SDLC_REPO_ROOT (repo fallback), SDLC_MCP_PYTHON (interpreter),
//! SDLC_MCP_ACTOR (validated actor override). Exit 2 on bad usage or an
//! invalid actor override, with the reason on stderr — stdout is the MCP
//! channel and carries protocol traffic only.

use std::process::ExitCode;

use kroker_mcp::actor;
use kroker_mcp::server::{Server, ServerConfig};
use rmcp::ServiceExt;

const USAGE: &str = "usage: kroker-mcp --repo <path> [--bridge-cmd <argv…>]";

fn parse_args() -> Result<ServerConfig, String> {
    let mut argv: Vec<String> = std::env::args().skip(1).collect();
    let mut repo: Option<String> = None;
    let mut bridge_cmd: Option<Vec<String>> = None;
    let mut i = 0;
    while i < argv.len() {
        match argv[i].as_str() {
            "--repo" => {
                let Some(value) = argv.get(i + 1) else {
                    return Err(format!("--repo needs a value; {USAGE}"));
                };
                repo = Some(value.clone());
                i += 2;
            }
            "--bridge-cmd" => {
                bridge_cmd = Some(argv.split_off(i + 1));
                argv.truncate(i);
                break;
            }
            other => return Err(format!("unknown argument {other:?}; {USAGE}")),
        }
    }
    let repo = repo
        .or_else(|| std::env::var("SDLC_REPO_ROOT").ok())
        .ok_or_else(|| format!("--repo is required (or set SDLC_REPO_ROOT); {USAGE}"))?;
    let actor_override = match std::env::var("SDLC_MCP_ACTOR") {
        Ok(value) if !value.is_empty() => Some(actor::validate_override(&value)?),
        _ => None,
    };
    Ok(ServerConfig {
        repo: std::path::PathBuf::from(repo),
        bridge_cmd,
        actor_override,
        now: None,
    })
}

fn main() -> ExitCode {
    // MCP owns stdout; tracing goes to stderr only (research R1).
    tracing_subscriber::fmt()
        .with_writer(std::io::stderr)
        .init();
    let cfg = match parse_args() {
        Ok(cfg) => cfg,
        Err(message) => {
            eprintln!("kroker-mcp: {message}");
            return ExitCode::from(2);
        }
    };
    let runtime = match tokio::runtime::Runtime::new() {
        Ok(rt) => rt,
        Err(e) => {
            eprintln!("kroker-mcp: could not start tokio: {e}");
            return ExitCode::from(1);
        }
    };
    runtime.block_on(async move {
        let server = Server::new(cfg);
        let service = match server.serve(rmcp::transport::stdio()).await {
            Ok(service) => service,
            Err(e) => {
                eprintln!("kroker-mcp: mcp stdio serve failed: {e}");
                std::process::exit(1);
            }
        };
        if let Err(e) = service.waiting().await {
            eprintln!("kroker-mcp: mcp service ended: {e}");
            std::process::exit(1);
        }
    });
    ExitCode::SUCCESS
}
