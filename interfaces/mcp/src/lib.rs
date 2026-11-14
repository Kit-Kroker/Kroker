//! kroker-mcp library: the MCP channel adapter behind the binary.
//!
//! Integration tests (tests/server.rs) import the modules from here; the
//! binary in main.rs is a thin launcher over `server::Server`.

pub mod actor;
pub mod bridge;
pub mod server;
