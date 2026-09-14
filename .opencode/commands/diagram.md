---
description: Create a diagram via the mashang-diagram router
agent: build
---

Use the `mashang-diagram` skill to fulfill the following request.

`mashang-diagram` is the router: it identifies the visual type, routes the
project's own types to `capabilities/diagram`, and delegates every other type
to the upstream `diagram-design` skill. Follow `diagram-design` as the source
of truth for general type rules, visual rules, and `self_check.py`.

Preserve the user's original intent and arguments.

$ARGUMENTS
