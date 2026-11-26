"""Notice a proxy that the server does not trust.

Behind a platform's proxy (Vercel, Railway, a load balancer) every request reaches the API from the proxy's address, unless the server is told which proxy to believe
(FORWARDED_ALLOW_IPS). Then all visitors share one rate limit bucket: a few people can lock everyone out of the sign in page and the tracked links. The symptom is easy to
see: the request carries an X-Forwarded-For header, and the address it came from is not one of the addresses in it. This counts both and says so in the settings page.
"""

from __future__ import annotations

import threading

MIN_SEEN = 5  # requests with the header before the app says anything


class ProxyWatch:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.seen = 0
        self.unexplained = 0

    def note(self, client_host: str | None, forwarded_for: str | None) -> None:
        if not forwarded_for:
            return
        hops = {h.strip() for h in forwarded_for.split(",") if h.strip()}
        with self._lock:
            self.seen += 1
            if client_host and client_host not in hops:  # the server did not take its address from the header, so it did not trust the sender
                self.unexplained += 1

    def problem(self) -> str | None:
        with self._lock:
            if self.seen >= MIN_SEEN and self.unexplained / self.seen > 0.8:
                return ("Requests arrive through a proxy that the server does not trust, so every visitor looks like the same address and shares one rate limit. "
                        "Set FORWARDED_ALLOW_IPS to the address of your proxy (see docs/04-ENVIRONMENT-VARIABLES.md) and restart the API.")
        return None
