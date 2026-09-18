"""Policy primitives for the agent runtime: canonicalization and URL/SSRF guard.

Everything in this subpackage is pure and side-effect free: no network, no
disk, no imports from the rest of NOVA. These are the pieces two machines must
agree on byte-for-byte (canonical.py) and the guard a future fetch tool must
route through (url_policy.py).
"""
