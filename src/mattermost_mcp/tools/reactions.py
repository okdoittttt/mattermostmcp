from __future__ import annotations

from typing import Any

from ..audit import audit_log
from ..safety import WriteGuard
from ..server import get_client, mcp, safe_call


@mcp.tool()
async def add_reaction(
    post_id: str, emoji_name: str, confirm: bool = False
) -> dict[str, Any]:
    """
    Add an emoji reaction (e.g. "thumbsup", "heart") to a post.

    ⚠️ This is an immediate WRITE operation visible to other users.
    Show the user what reaction will be added and obtain explicit approval first.

    Args:
        post_id: The post to react to.
        emoji_name: Mattermost emoji name without colons (e.g. "thumbsup", not ":thumbsup:").
        confirm: Must be True for the reaction to be added.

    Returns:
        On success: {"status": "added", "post_id": "...", "emoji": "..."}
    """
    blocker = WriteGuard.require_confirmation(
        confirm, "add_reaction", f"{post_id}:{emoji_name}"
    )
    if blocker is not None:
        return blocker

    def _do() -> dict[str, Any]:
        client = get_client()
        client.add_reaction(post_id, emoji_name)
        audit_log("add_reaction", post_id=post_id, emoji=emoji_name, user=client.my_username)
        return {"status": "added", "post_id": post_id, "emoji": emoji_name}

    return safe_call(_do)


@mcp.tool()
async def remove_reaction(
    post_id: str, emoji_name: str, confirm: bool = False
) -> dict[str, Any]:
    """
    Remove your own reaction (you can only remove your own) from a post.

    ⚠️ This is an immediate WRITE operation. Confirm with the user first.

    Args:
        post_id: The post to un-react.
        emoji_name: Mattermost emoji name without colons.
        confirm: Must be True for the reaction to be removed.

    Returns:
        On success: {"status": "removed", "post_id": "...", "emoji": "..."}
    """
    blocker = WriteGuard.require_confirmation(
        confirm, "remove_reaction", f"{post_id}:{emoji_name}"
    )
    if blocker is not None:
        return blocker

    def _do() -> dict[str, Any]:
        client = get_client()
        client.remove_reaction(post_id, emoji_name)
        audit_log("remove_reaction", post_id=post_id, emoji=emoji_name, user=client.my_username)
        return {"status": "removed", "post_id": post_id, "emoji": emoji_name}

    return safe_call(_do)
