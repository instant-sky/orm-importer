from decimal import Decimal

import osmium
import overpy


def _parse_poly_string(polygon: str) -> list[tuple[float, float]]:
    # Overpass poly strings are "lat lon lat lon ..."
    values = [float(v) for v in polygon.split()]
    return list(zip(values[0::2], values[1::2]))


def _point_in_polygon(lat: float, lon: float, polygon: list[tuple[float, float]]) -> bool:
    # ray casting, the polygon does not need to be closed
    inside = False
    j = len(polygon) - 1
    for i in range(len(polygon)):
        lat_i, lon_i = polygon[i]
        lat_j, lon_j = polygon[j]
        if (lat_i > lat) != (lat_j > lat) and lon < (lon_j - lon_i) * (lat - lat_i) / (lat_j - lat_i) + lon_i:
            inside = not inside
        j = i
    return inside


def load_from_osm_file(osm_file: str, polygon: str, railway_option_types: list[str]) -> overpy.Result:
    """
    Local replacement for the Overpass query in ORMImporter._get_track_objects.
    Works on any OSM file, e.g. a pre-filtered germany-railway.osm.pbf or a
    dated Geofabrik snapshot.
    """
    poly = _parse_poly_string(polygon)
    railway_types = set(railway_option_types)

    # pass 1: railway ways with at least one node inside the polygon
    # (same as `osmium extract -s complete_ways`)
    ways: dict[int, tuple[list[int], dict[str, str]]] = {}
    for way in osmium.FileProcessor(osm_file).with_locations():
        if not way.is_way() or way.tags.get("railway") not in railway_types:
            continue
        if any(
            ref.location.valid() and _point_in_polygon(ref.location.lat, ref.location.lon, poly)
            for ref in way.nodes
        ):
            ways[way.id] = ([ref.ref for ref in way.nodes], dict(way.tags))

    # pass 2: all nodes of these ways, also those outside the polygon (like Overpass `node(w)`)
    node_ids = {node_id for node_ids, _ in ways.values() for node_id in node_ids}
    result = overpy.Result()
    for node in osmium.FileProcessor(osm_file, osmium.osm.NODE).with_filter(osmium.filter.IdFilter(node_ids)):
        result.append(
            overpy.Node(
                node_id=node.id,
                lat=Decimal(str(node.location.lat)),
                lon=Decimal(str(node.location.lon)),
                tags=dict(node.tags),
                attributes={},
                result=result,
            )
        )
    for way_id, (way_node_ids, tags) in ways.items():
        result.append(overpy.Way(way_id=way_id, node_ids=way_node_ids, tags=tags, attributes={}, result=result))
    return result
