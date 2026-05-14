from __future__ import annotations

from typing import Any

from ..audit import audit_log
from ..safety import WriteGuard, external_user_input, get_blocked_channels
from ..server import get_client, mcp, safe_call

MAX_LIMIT = 200
DEFAULT_LIMIT = 30


@mcp.tool()
async def list_my_channels(team_name: str | None = None) -> dict[str, Any]:
    """
    List Mattermost channels the authenticated user is a member of.

    Use this when the user asks about their channels, wants to find a channel ID,
    or needs context before sending messages.

    Args:
        team_name: Optional team URL-name (e.g. "engineering") to scope the result.
                   When omitted, returns channels across all teams the user belongs to.

    Returns:
        {"teams": [{"team": {"id","name","display_name"}, "channels": [...]}]}
        Each channel: {"id","name","display_name","type"} where type is "O" (public),
        "P" (private), "D" (DM), "G" (group DM).
    """

    def _do() -> dict[str, Any]:
        client = get_client()
        teams = client.get_user_teams()
        if team_name:
            teams = [t for t in teams if t["name"] == team_name]
            if not teams:
                return {
                    "error": "team_not_found",
                    "hint": f"Team '{team_name}' not found among your teams.",
                }
        blocked = get_blocked_channels()
        result: list[dict[str, Any]] = []
        for team in teams:
            channels = client.get_channels_for_user(team["id"])
            visible = [
                {
                    "id": c["id"],
                    "name": c["name"],
                    "display_name": c.get("display_name", c["name"]),
                    "type": c.get("type", "O"),
                }
                for c in channels
                if c.get("name") not in blocked
            ]
            result.append(
                {
                    "team": {
                        "id": team["id"],
                        "name": team["name"],
                        "display_name": team.get("display_name", team["name"]),
                    },
                    "channels": visible,
                }
            )
        return {"teams": result}

    return safe_call(_do)


@mcp.tool()
async def get_unread_summary() -> dict[str, Any]:
    """
    List channels with unread messages, sorted by mention count (descending).

    Use this to answer "what should I catch up on?" type questions before drilling into
    specific channels.

    Returns:
        {"channels": [{"channel_id","name","display_name","unread","mentions"}]}
        Sorted by mentions desc, then unread desc. Empty list means everything is read.
    """

    def _do() -> dict[str, Any]:
        client = get_client()
        teams = client.get_user_teams()
        blocked = get_blocked_channels()
        rows: list[dict[str, Any]] = []
        for team in teams:
            channels = client.get_channels_for_user(team["id"])
            for ch in channels:
                if ch.get("name") in blocked:
                    continue
                try:
                    unread = client.get_channel_unread(ch["id"])
                except Exception:
                    continue
                msg_count = unread.get("msg_count", 0)
                mention_count = unread.get("mention_count", 0)
                if msg_count == 0 and mention_count == 0:
                    continue
                rows.append(
                    {
                        "channel_id": ch["id"],
                        "name": ch.get("name"),
                        "display_name": ch.get("display_name", ch.get("name")),
                        "team_name": team.get("name"),
                        "unread": msg_count,
                        "mentions": mention_count,
                    }
                )
        rows.sort(key=lambda r: (-r["mentions"], -r["unread"]))
        return {"channels": rows}

    return safe_call(_do)


@mcp.tool()
async def open_dm(username: str) -> dict[str, Any]:
    """
    Open (or fetch) the direct-message channel between you and another user.

    This does NOT send a message — it only returns the channel_id so a subsequent
    send_message call can target the DM. Idempotent and safe to call without confirm.

    Args:
        username: The other user's Mattermost username (without leading @).

    Returns:
        {"channel_id": "...", "username": "..."}
    """

    def _do() -> dict[str, Any]:
        client = get_client()
        other = client.get_user_by_username(username)
        ch = client.create_direct_message_channel(other["id"])
        return {"channel_id": ch["id"], "username": other["username"]}

    return safe_call(_do)


@mcp.tool()
async def join_channel(channel_id: str, confirm: bool = False) -> dict[str, Any]:
    """
    Join a public channel by its channel_id.

    ⚠️ This is an immediate WRITE operation that adds you as a channel member.
    You MUST confirm with the user first and only call again with confirm=True.

    Args:
        channel_id: The channel ID to join. Use list_my_channels or search to find it.
        confirm: Must be True for the join to actually happen.

    Returns:
        On success: {"status": "joined", "channel_id": "..."}
    """
    blocker = WriteGuard.require_confirmation(confirm, "join_channel", channel_id)
    if blocker is not None:
        return blocker

    def _do() -> dict[str, Any]:
        client = get_client()
        client.add_user_to_channel(channel_id, client.my_id)
        audit_log("join_channel", channel_id=channel_id, user=client.my_username)
        return {"status": "joined", "channel_id": channel_id}

    return safe_call(_do)


@mcp.tool()
async def leave_channel(channel_id: str, confirm: bool = False) -> dict[str, Any]:
    """
    Leave a channel by its channel_id.

    ⚠️ This is an immediate WRITE operation that removes you from the channel.
    You MUST confirm with the user first and only call again with confirm=True.

    Args:
        channel_id: The channel ID to leave.
        confirm: Must be True for the leave to actually happen.

    Returns:
        On success: {"status": "left", "channel_id": "..."}
    """
    blocker = WriteGuard.require_confirmation(confirm, "leave_channel", channel_id)
    if blocker is not None:
        return blocker

    def _do() -> dict[str, Any]:
        client = get_client()
        client.remove_user_from_channel(channel_id, client.my_id)
        audit_log("leave_channel", channel_id=channel_id, user=client.my_username)
        return {"status": "left", "channel_id": channel_id}

    return safe_call(_do)
