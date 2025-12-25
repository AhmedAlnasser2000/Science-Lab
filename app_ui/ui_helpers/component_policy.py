from typing import Optional


class WorkspaceComponentPolicy:
    def __init__(self) -> None:
        self.enabled_pack_ids: set[str] = set()
        self.available_pack_ids: set[str] = set()
        self.disabled_component_ids: set[str] = set()

    def update(
        self,
        *,
        enabled_pack_ids: set[str],
        available_pack_ids: set[str],
        disabled_component_ids: set[str],
    ) -> None:
        self.enabled_pack_ids = set(enabled_pack_ids)
        self.available_pack_ids = set(available_pack_ids)
        self.disabled_component_ids = set(disabled_component_ids)

    def is_pack_enabled(self, pack_id: Optional[str]) -> bool:
        if not pack_id:
            return True
        if not self.enabled_pack_ids:
            return pack_id in self.available_pack_ids if self.available_pack_ids else True
        return pack_id in self.enabled_pack_ids

    def is_component_enabled(self, component_id: Optional[str]) -> bool:
        if not component_id:
            return True
        return component_id not in self.disabled_component_ids


_WORKSPACE_COMPONENT_POLICY: Optional[WorkspaceComponentPolicy] = None


def _set_global_component_policy(policy: WorkspaceComponentPolicy) -> None:
    global _WORKSPACE_COMPONENT_POLICY
    _WORKSPACE_COMPONENT_POLICY = policy


def _get_global_component_policy() -> Optional[WorkspaceComponentPolicy]:
    return _WORKSPACE_COMPONENT_POLICY
