from app.db.models import Trip


def requires_intercity_transport(trip: Trip) -> bool:
    """New trips use canonical city-level adcodes as the only city identity."""
    if trip.city_adcode and trip.origin_city_adcode:
        return trip.city_adcode != trip.origin_city_adcode
    # Keep already-created trips usable until users recreate or edit them with
    # canonical selections. New trips can never enter this fallback branch.
    return bool(
        trip.origin_city
        and trip.city
        and trip.origin_city.strip() != trip.city.strip()
    )
