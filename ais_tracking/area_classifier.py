def get_vessel_area(lat, lon):
    """Return an approximate maritime area based on AIS coordinates."""
    try:
        lat = float(lat)
        lon = float(lon)
    except (TypeError, ValueError):
        return "Unknown area", "Unknown"

    # Southern Peninsula / Singapore Strait
    if 1.15 <= lat <= 1.50 and 103.5 <= lon <= 104.2:
        return "Johor / Singapore Strait vicinity", "Southern Peninsula"

    # Sabah
    if 5.7 <= lat <= 6.3 and 115.8 <= lon <= 116.4:
        return "Kota Kinabalu vicinity", "Sabah"

    if 4.0 <= lat <= 7.5 and 115.0 <= lon <= 120.5:
        return "Sabah coastal region", "Sabah"

    # Sarawak
    if 1.0 <= lat <= 5.0 and 109.0 <= lon <= 115.5:
        return "Sarawak coastal region", "Sarawak"

    # West coast of Peninsular Malaysia
    if 2.5 <= lat <= 3.5 and 100.5 <= lon <= 102.0:
        return "Port Klang / Selangor vicinity", "Selangor"

    if 4.0 <= lat <= 5.5 and 99.5 <= lon <= 101.5:
        return "Perak / Penang coastal vicinity", "Northern Peninsula"

    # East coast of Peninsular Malaysia
    if 3.0 <= lat <= 5.0 and 103.0 <= lon <= 105.0:
        return "Pahang / Terengganu coastal vicinity", "East Coast"

    if 5.0 <= lat <= 7.0 and 102.0 <= lon <= 104.5:
        return "Kelantan / Terengganu coastal vicinity", "East Coast"

    return "Other maritime area", "Other"
