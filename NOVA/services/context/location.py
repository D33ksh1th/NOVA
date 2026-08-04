"""
Location Context
"""

import geocoder


class LocationContext:

    def build(self):

        try:

            g = geocoder.ip("me")

            return {

                "city": g.city,

                "state": g.state,

                "country": g.country,

                "latitude": g.latlng[0] if g.latlng else None,

                "longitude": g.latlng[1] if g.latlng else None,

            }

        except Exception:

            return {
                "city": None,
                "state": None,
                "country": None,
            }