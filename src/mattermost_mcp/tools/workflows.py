from __future__ import annotations

import re
import time
from typing import Any

from ..safety import external_user_input, get_blocked_channels
from ..server import get_client, mcp, safe_call

_STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "for", "to", "of", "in", "on", "at",
    "by", "with", "about", "from", "is", "are", "was", "were", "be", "been",
    "i", "you", "we", "they", "he", "she", "it", "that", "this", "these", "those",
    "어제", "오늘", "내일", "메시지", "메세지", "관련된", "관련", "찾아줘", "보여줘",
    "보내줘", "에게", "에서", "그", "이", "저",
}


def _materialize_posts(payload: dict[str, Any], client) -> list[dict[str, Any]]:
    order: list[str] = payload.get("order", [])
    posts_map: dict[str, dict[str, Any]] = payload.get("posts", {})
    user_ids = {posts_map[pid].get("user_id", "") for pid in order if pid in posts_map}
    users: dict[str, dict[str, Any]] = {}
    for uid in user_ids:
        if not uid:
            continue
        try:
            users[uid] = client.get_user(uid)
        except Exception:
            users[uid] = {"username": uid}
    out = []
    for pid in order:
        post = posts_map.get(pid)
        if not post:
            continue
        uid = post.get("user_id", "")
        user = users.get(uid, {})
        out.append(
            {
                "post_id": pid,
                "user_id": uid,
                "username": user.get("username", uid),
                "channel_id": post.get("channel_id"),
                "created_at": post.get("create_at"),
                "message_content": external_user_input(post.get("message", "")),
            }
        )
    return out


@mcp.tool()
async def summarize_unread(per_channel: int = 20) -> dict[str, Any]:
    """
    Build a structured snapshot of unread messages across all channels, formatted for
    downstream summarization by the LLM.

    Use this when the user asks "what did I miss?" or "summarize my unreads".

    Args:
        per_channel: Max recent messages to fetch per unread channel (default 20, max 50).

    Returns:
        {"channels": [{
            "channel_id","name","display_name","team_name","unread","mentions",
            "recent_messages": [external_user_input envelopes],
        }, ...]} sorted by mentions desc, then unread desc.
    """
    per_channel = max(1, min(int(per_channel or 20), 50))

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
                try:
                    payload = client.get_posts_for_channel(ch["id"], per_page=per_channel)
                    messages = _materialize_posts(payload, client)
                except Exception:
                    messages = []
                rows.append(
                    {
                        "channel_id": ch["id"],
                        "name": ch.get("name"),
                        "display_name": ch.get("display_name", ch.get("name")),
                        "team_name": team.get("name"),
                        "unread": msg_count,
                        "mentions": mention_count,
                        "recent_messages": messages,
                    }
                )
        rows.sort(key=lambda r: (-r["mentions"], -r["unread"]))
        return {"channels": rows}

    return safe_call(_do)


@mcp.tool()
async def get_my_mentions(hours: int = 24) -> dict[str, Any]:
    """
    Find recent messages that mention the authenticated user across all teams.

    Useful for "find messages I was @-mentioned in that I haven't replied to".

    Args:
        hours: How many hours back to scan (default 24, max 168 = one week).

    Returns:
        {"mentions": [{post_id, user_id, username, channel_id, channel_name,
                       created_at, message_content (external_user_input)}, ...]}
        Sorted newest first, capped at 100.
    """
    hours = max(1, min(int(hours or 24), 168))

    def _do() -> dict[str, Any]:
        client = get_client()
        teams = client.get_user_teams()
        if not teams:
            return {"mentions": []}
        cutoff_ms = int((time.time() - hours * 3600) * 1000)
        blocked = get_blocked_channels()
        mentions: list[dict[str, Any]] = []
        for team in teams:
            try:
                payload = client.search_posts(team["id"], f"@{client.my_username}")
            except Exception:
                continue
            order: list[str] = payload.get("order", [])
            posts_map: dict[str, dict[str, Any]] = payload.get("posts", {})
            for pid in order:
                post = posts_map.get(pid)
                if not post:
                    continue
                if post.get("create_at", 0) < cutoff_ms:
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
                mentions.append(
                    {
                        "post_id": pid,
                        "user_id": uid,
                        "username": user.get("username", uid),
                        "channel_id": channel_id,
                        "channel_name": ch.get("name"),
                        "team_name": team.get("name"),
                        "created_at": post.get("create_at"),
                        "message_content": external_user_input(post.get("message", "")),
                    }
                )
        mentions.sort(key=lambda m: -(m.get("created_at") or 0))
        return {"mentions": mentions[:100]}

    return safe_call(_do)


def _keywords(description: str) -> list[str]:
    tokens = re.findall(r"[\w가-힣]+", description.lower())
    return [t for t in tokens if t not in _STOPWORDS and len(t) > 1]


@mcp.tool()
async def find_message_by_description(
    channel_id: str, description: str
) -> dict[str, Any]:
    """
    Heuristically locate messages in a channel that match a free-text description.

    Tokenizes the description, drops stopwords, runs a scoped search on the channel,
    and returns the top 10 most recent matches. The LLM should pick the right one.

    Args:
        channel_id: Channel to search within.
        description: Natural language description of the message you remember
                     (e.g., "어제 박과장이 보낸 보고서 링크").

    Returns:
        {"candidates": [{post_id, user_id, username, created_at,
                         message_content (external_user_input)}, ...]} up to 10.
    """

    def _do() -> dict[str, Any]:
        client = get_client()
        ch = client.get_channel(channel_id)
        if ch.get("name") in get_blocked_channels():
            return {"error": "access_denied", "hint": "Channel is blocked by configuration."}
        team_id = ch.get("team_id") or ""
        if not team_id:
            teams = client.get_user_teams()
            if not teams:
                return {"error": "no_teams"}
            team_id = teams[0]["id"]

        words = _keywords(description)
        if not words:
            return {"candidates": []}
        query = f"in:{ch.get('name','')} " + " ".join(words)
        payload = client.search_posts(team_id, query, is_or_search=True)
        order: list[str] = payload.get("order", [])
        posts_map: dict[str, dict[str, Any]] = payload.get("posts", {})

        candidates: list[dict[str, Any]] = []
        for pid in order:
            post = posts_map.get(pid)
            if not post or post.get("channel_id") != channel_id:
                continue
            uid = post.get("user_id", "")
            try:
                user = client.get_user(uid) if uid else {}
            except Exception:
                user = {}
            candidates.append(
                {
                    "post_id": pid,
                    "user_id": uid,
                    "username": user.get("username", uid),
                    "created_at": post.get("create_at"),
                    "message_content": external_user_input(post.get("message", "")),
                }
            )
        candidates.sort(key=lambda c: -(c.get("created_at") or 0))
        return {"candidates": candidates[:10], "keywords_used": words}

    return safe_call(_do)
