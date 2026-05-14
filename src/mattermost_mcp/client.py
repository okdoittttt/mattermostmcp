from __future__ import annotations

from typing import Any

from mattermostdriver import Driver

from .auth import AuthProvider
from .cache import LRUCache


class MattermostClient:
    def __init__(self, auth: AuthProvider) -> None:
        self._auth = auth
        self._driver: Driver | None = None
        self._user_cache = LRUCache(maxsize=256, ttl=300.0)
        self._channel_cache = LRUCache(maxsize=256, ttl=300.0)
        self._team_cache = LRUCache(maxsize=64, ttl=300.0)
        self._logged_in = False
        self.my_id: str | None = None
        self.my_username: str | None = None

    def _driver_obj(self) -> Driver:
        if self._driver is None:
            self._driver = Driver(self._auth.driver_config())
        return self._driver

    def login(self) -> None:
        if self._logged_in:
            return
        drv = self._driver_obj()
        me = drv.login()
        self.my_id = me["id"]
        self.my_username = me["username"]
        self._logged_in = True

    def _ensure(self) -> Driver:
        if not self._logged_in:
            self.login()
        assert self._driver is not None
        return self._driver

    # --- users ---
    def get_user(self, user_id: str) -> dict[str, Any]:
        cached = self._user_cache.get(("id", user_id))
        if cached is not None:
            return cached
        drv = self._ensure()
        user = drv.users.get_user(user_id)
        self._user_cache.set(("id", user_id), user)
        self._user_cache.set(("name", user["username"]), user)
        return user

    def get_user_by_username(self, username: str) -> dict[str, Any]:
        cached = self._user_cache.get(("name", username))
        if cached is not None:
            return cached
        drv = self._ensure()
        user = drv.users.get_user_by_username(username)
        self._user_cache.set(("name", username), user)
        self._user_cache.set(("id", user["id"]), user)
        return user

    def search_users(self, term: str, team_id: str | None = None) -> list[dict[str, Any]]:
        drv = self._ensure()
        options: dict[str, Any] = {"term": term, "allow_inactive": False}
        if team_id:
            options["team_id"] = team_id
        return drv.users.search_users(options=options) or []

    # --- teams ---
    def get_user_teams(self) -> list[dict[str, Any]]:
        cached = self._team_cache.get(("mine",))
        if cached is not None:
            return cached
        drv = self._ensure()
        teams = drv.teams.get_user_teams(self.my_id) or []
        self._team_cache.set(("mine",), teams)
        for team in teams:
            self._team_cache.set(("name", team["name"]), team)
            self._team_cache.set(("id", team["id"]), team)
        return teams

    def get_team_by_name(self, name: str) -> dict[str, Any] | None:
        cached = self._team_cache.get(("name", name))
        if cached is not None:
            return cached
        for team in self.get_user_teams():
            if team["name"] == name:
                return team
        return None

    # --- channels ---
    def get_channel(self, channel_id: str) -> dict[str, Any]:
        cached = self._channel_cache.get(("id", channel_id))
        if cached is not None:
            return cached
        drv = self._ensure()
        ch = drv.channels.get_channel(channel_id)
        self._channel_cache.set(("id", channel_id), ch)
        return ch

    def get_channel_by_name(self, team_id: str, name: str) -> dict[str, Any]:
        cached = self._channel_cache.get(("teamname", team_id, name))
        if cached is not None:
            return cached
        drv = self._ensure()
        ch = drv.channels.get_channel_by_name(team_id, name)
        self._channel_cache.set(("teamname", team_id, name), ch)
        self._channel_cache.set(("id", ch["id"]), ch)
        return ch

    def get_channels_for_user(self, team_id: str) -> list[dict[str, Any]]:
        drv = self._ensure()
        return drv.channels.get_channels_for_user(self.my_id, team_id) or []

    def get_channel_unread(self, channel_id: str) -> dict[str, Any]:
        drv = self._ensure()
        return drv.channels.get_unread_messages(self.my_id, channel_id)

    def create_direct_message_channel(self, other_user_id: str) -> dict[str, Any]:
        drv = self._ensure()
        return drv.channels.create_direct_message_channel([self.my_id, other_user_id])

    def add_user_to_channel(self, channel_id: str, user_id: str) -> dict[str, Any]:
        drv = self._ensure()
        return drv.channels.add_user(channel_id, options={"user_id": user_id})

    def remove_user_from_channel(self, channel_id: str, user_id: str) -> Any:
        drv = self._ensure()
        return drv.channels.remove_channel_member(channel_id, user_id)

    # --- posts ---
    def get_posts_for_channel(
        self,
        channel_id: str,
        per_page: int = 30,
        before: str | None = None,
    ) -> dict[str, Any]:
        drv = self._ensure()
        params: dict[str, Any] = {"per_page": per_page}
        if before:
            params["before"] = before
        return drv.posts.get_posts_for_channel(channel_id, params=params)

    def get_thread(self, post_id: str) -> dict[str, Any]:
        drv = self._ensure()
        return drv.posts.get_thread(post_id)

    def create_post(
        self, channel_id: str, message: str, root_id: str | None = None
    ) -> dict[str, Any]:
        drv = self._ensure()
        body: dict[str, Any] = {"channel_id": channel_id, "message": message}
        if root_id:
            body["root_id"] = root_id
        return drv.posts.create_post(options=body)

    def update_post(self, post_id: str, message: str) -> dict[str, Any]:
        drv = self._ensure()
        return drv.posts.update_post(
            post_id, options={"id": post_id, "message": message}
        )

    def delete_post(self, post_id: str) -> Any:
        drv = self._ensure()
        return drv.posts.delete_post(post_id)

    def search_posts(
        self, team_id: str, query: str, is_or_search: bool = False
    ) -> dict[str, Any]:
        drv = self._ensure()
        return drv.posts.search_for_team_posts(
            team_id, options={"terms": query, "is_or_search": is_or_search}
        )

    # --- reactions ---
    def add_reaction(self, post_id: str, emoji_name: str) -> dict[str, Any]:
        drv = self._ensure()
        return drv.reactions.create_reaction(
            options={
                "user_id": self.my_id,
                "post_id": post_id,
                "emoji_name": emoji_name,
            }
        )

    def remove_reaction(self, post_id: str, emoji_name: str) -> Any:
        drv = self._ensure()
        return drv.reactions.delete_reaction(self.my_id, post_id, emoji_name)
