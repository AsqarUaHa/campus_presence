from geopy.distance import distance

def is_within_radius(user_lat, user_lon, target_lat, target_lon, radius_m):
    return distance((user_lat, user_lon), (target_lat, target_lon)).meters <= radius_m

