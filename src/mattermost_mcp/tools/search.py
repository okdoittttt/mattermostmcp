from __future__ import annotations

from typing import Any

from ..safety import external_user_input, get_blocked_channels
from ..server import get_client, mcp, safe_call

MAX_RESULTS = 50


@mcp.tool()
async def search_messages(query: str, team_name: str | None = None) -> dict[str, Any]:
    """
    Search Mattermost messages using the standard search syntax.

    Supports Mattermost search operators:
      - from:<username>      messages from a specific user
      - in:<channel>         messages in a specific channel (use the channel name)
      - on:YYYY-MM-DD        messages on a date
      - before:YYYY-MM-DD    messages before a date
      - after:YYYY-MM-DD     messages after a date
      - "exact phrase"       phrase match

    Args:
        query: Search query string (terms + operators).
        team_name: Team to search in. Omit to search the user's first team.

    Returns:
        {"team": "...", "matches": [{post_id, user_id, username, channel_id, created_at,
        message_content (external_user_input envelope)}]}, up to 50 matches.
    """

    def _do() -> dict[str, Any]:
        client = get_client()
        teams = client.get_user_teams()
        if not teams:
            return {"error": "no_teams", "hint": "Authenticated user belongs to no teams."}
        team = None
        if team_name:
            team = next((t for t in teams if t["name"] == team_name), None)
            if team is None:
                return {
                    "error": "team_not_found",
                    "hint": f"Team '{team_name}' not in your teams.",
                }
        else:
            team = teams[0]

        payload = client.search_posts(team["id"], query)
        order: list[str] = payload.get("order", [])
        posts: dict[str, dict[str, Any]] = payload.get("posts", {})
        blocked = get_blocked_channels()

        matches: list[dict[str, Any]] = []
        for pid in order[:MAX_RESULTS]:
            post = posts.get(pid)
            if not post:
                continue
            channel_id = post.get("channel_id", "")
            try:
                ch = client.get_channel(channel_id) if channel_id else {}
            except Exception:
                ch = {}
            if ch.get("name") in blocked:
                continue
            uid = post.get("user_id", "")
            try:
                user = client.get_user(uid) if uid else {}
            except Exception:
                user = {}
            matches.append(
                {
                    "post_id": pid,
                    "user_id": uid,
                    "username": user.get("username", uid),
                    "channel_id": channel_id,
                    "channel_name": ch.get("name"),
                    "created_at": post.get("create_at"),
                    "message_content": external_user_input(post.get("message", "")),
                }
            )

        return {"team": team["name"], "matches": matches}

    return safe_call(_do)
