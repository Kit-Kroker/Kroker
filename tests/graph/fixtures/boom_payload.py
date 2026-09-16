"""A payload module whose import crashes (E-74: check_node_types runs at worker boot)."""

raise RuntimeError("import-time crash")
