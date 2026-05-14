from __future__ import annotations

from typing import Any

from ..server import get_client, mcp, safe_call


def _format_user(user: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": user.get("id"),
        "username": user.get("username"),
        "first_name": user.get("first_name"),
        "last_name": user.get("last_name"),
        "nickname": user.get("nickname"),
        "email": user.get("email"),
        "position": user.get("position"),
    }


@mcp.tool()
async def find_user(query: str) -> dict[str, Any]:
    """
    Search for Mattermost users by username, first name, last name, or nickname.

    Use this when the user refers to someone by name and you need a username or user_id
    before sending a DM or mentioning them.

    Args:
        query: A search term — partial username, first name, last name, or nickname.

    Returns:
        {"users": [{"id","username","first_name","last_name",...}, ...]}
        Up to 20 matches.
    """

    def _do() -> dict[str, Any]:
        client = get_client()
        users = client.search_users(query)
        return {"users": [_format_user(u) for u in users[:20]]}

    return safe_call(_do)


@mcp.tool()
async def get_user_info(username: str) -> dict[str, Any]:
    """
    Get detailed profile information for a single user by exact username.

    Args:
        username: The user's exact Mattermost username (no leading @).

    Returns:
        {"id","username","first_name","last_name","nickname","email","position"}
    """

    def _do() -> dict[str, Any]:
        client = get_client()
        user = client.get_user_by_username(username)
        return _format_user(user)

    return safe_call(_do)


@mcp.tool()
async def whoami() -> dict[str, Any]:
    """
    Return the authenticated user's username and id. Use this to confirm which account
    the MCP server is connected as.

    Returns:
        {"id": "...", "username": "..."}
    """

    def _do() -> dict[str, Any]:
        client = get_client()
        return {"id": client.my_id, "username": client.my_username}

    return safe_call(_do)
