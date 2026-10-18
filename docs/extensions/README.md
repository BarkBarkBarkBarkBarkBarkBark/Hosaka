# Hosaka extensions

Start with the [agent guide](AGENT_GUIDE.md) and
[implemented specification](SPECIFICATION.md).

**Available now:** package authoring, strict non-executing validation, discovery,
private registration metadata and lifecycle management. Source/appliance/Docker
setup seeds a standalone reference package, disabled and without grants. Existing
packages, saved data, enablement and grants are preserved.

**Available after explicit approval:** trusted-local `run`, scoped data/log
context, runtime schema checks, safe mode/cancellation, authenticated generic API
and host-rendered declarative Menu views. `enable` remains separate from trust
and grants. Root/public execution is refused.

**Not yet available:** an OS sandbox, enforced network/process/host-filesystem
restrictions, `extensions test`, dedicated agent tools or archive upgrades.
Approved Python retains user privileges; inspect it before trusting its digest.

See [security boundaries](SECURITY.md), [testing](TESTING.md) and the
[full roadmap](../extension_plan.md). The independent
[reference source](../../examples/extensions/reference-extension/) contains real
callable actions and local tests. See the specification for approval and running.
