"""
Location Context
"""

import geocoder


class LocationContext:

    def build(self):

        try:

            g = geocoder.ip("me")

            city = g.city or None
            state = g.state or None
            country = g.country or None

            # geocoder sometimes succeeds but returns all-None fields when the
            # IP lookup service is rate-limited or blocked. Treat that as a
            # failure so callers get a clean "Unknown city" instead of "None".
            if not city and not country:
                raise ValueError("geocoder returned empty location data")

            return {
                "city": city,
                "state": state,
                "country": country,
                "latitude": g.latlng[0] if g.latlng else None,
                "longitude": g.latlng[1] if g.latlng else None,
            }

        except Exception:

            return {
                "city": "Unknown city",
                "state": "",
                "country": "Unknown country",
                "latitude": None,
                "longitude": None,
            }