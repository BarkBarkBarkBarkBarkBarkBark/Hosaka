# Hosaka extensions

Start with the [agent guide](AGENT_GUIDE.md) and
[implemented specification](SPECIFICATION.md).

**Available now:** package authoring, strict non-executing validation, discovery,
private registration metadata and lifecycle management. Source/appliance/Docker
setup seeds a standalone reference package, disabled and without grants. Existing
packages, saved data, enablement and grants are preserved.

**Not yet available:** execution through Hosaka, `extensions run`/`test`, a
production context, authenticated extension API, rendered extension menus/views,
agent action dispatch, enforced permissions, sandbox or safe mode. The current
`enable` command changes metadata only; it does not authorize or execute code.

See [security boundaries](SECURITY.md), [testing](TESTING.md) and the
[full roadmap](../extension_plan.md). The independent
[reference source](../../examples/extensions/reference-extension/) contains real
callable actions and local tests, not a host integration claim.
