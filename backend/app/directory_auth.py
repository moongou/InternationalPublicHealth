from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse

from ldap3 import Connection, NONE, Server
from ldap3.utils.conv import escape_filter_chars

from .config import Settings


@dataclass(frozen=True)
class DirectoryIdentity:
    username: str
    display_name: str


class LdapAuthenticator:
    """LDAP/AD password authenticator using a read-only search account.

    The service bind locates the user's DN; credentials are then verified by a
    second bind as that user. Passwords are never stored or logged locally.
    """

    def __init__(self, settings: Settings):
        self.settings = settings
        self.enabled = settings.auth_mode == "local+ldap"

    def authenticate(self, username: str, password: str) -> DirectoryIdentity | None:
        if not self.enabled or not username or not password:
            return None
        parsed = urlparse(self.settings.ldap_server_url)
        use_ssl = parsed.scheme.lower() == "ldaps"
        server = Server(
            parsed.hostname or self.settings.ldap_server_url,
            port=parsed.port or (636 if use_ssl else 389),
            use_ssl=use_ssl,
            get_info=NONE,
            connect_timeout=5,
        )
        service = Connection(
            server,
            user=self.settings.ldap_bind_dn,
            password=self.settings.ldap_bind_password,
            auto_bind=True,
            receive_timeout=5,
        )
        try:
            search_filter = self.settings.ldap_user_filter.format(username=escape_filter_chars(username))
            if not service.search(
                self.settings.ldap_base_dn,
                search_filter,
                attributes=["displayName", "cn", "sAMAccountName", "uid"],
                size_limit=2,
            ) or len(service.entries) != 1:
                return None
            entry = service.entries[0]
            user_dn = entry.entry_dn
            display_name = str(entry.displayName) if "displayName" in entry and entry.displayName else str(entry.cn)
        finally:
            service.unbind()
        user_connection = Connection(
            server, user=user_dn, password=password, auto_bind=True, receive_timeout=5,
        )
        try:
            return DirectoryIdentity(username=username, display_name=display_name or username)
        finally:
            user_connection.unbind()
