import math


def rh_from_dewpoint(dewpoint, temperature):
    """Relative humidity (%) from dew point and temperature (°C), Magnus formula, valid -40 to 60 °C."""
    if dewpoint >= temperature:
        return 100.0
    a = 17.625
    b = 243.04
    rh = 100.0 * math.exp(a * dewpoint / (b + dewpoint)) / math.exp(a * temperature / (b + temperature))
    return max(0.0, min(100.0, rh))


def calibrated_rh(rh):
    """Correct the RH at the external (cell) temperature to the real RH inside the cell.
    Fit from deliquescence of pure salts, version 09 June 2026.
    """
    return 0.9641 * rh + 1.2871
