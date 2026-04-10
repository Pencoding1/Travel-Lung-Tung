from enum import Enum

class CACHE_MODE(str, Enum):
    WRITE = "write"
    READ = "read"

class City(str, Enum):
    HCM = "hcm"
    HANOI = "hanoi"
    DALAT = "dalat"
    DANANG = "danang"


class Agency(str, Enum):
    TRAVELOKA = "traveloka"
    VIETRAVEL = "vietravel"
    VIETNAM_CORACLE = "vietnamcoracle"
    VIETNAM_TRAVEL = "vietnam_travel"

