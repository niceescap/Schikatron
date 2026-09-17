"""Pure-Python projected geometry and single-cycle sampling."""
import math
from . import __version__

STATES = list(range(0, 360, 30))
ANGLE_POINTS = {
    "knee_internal": ("hip", "knee", "ankle"),
    "hip_trunk_thigh_internal": ("shoulder", "hip", "knee"),
    "elbow_internal": ("shoulder", "elbow", "wrist"),
    "ankle_shank_forefoot_internal": ("knee", "ankle", "forefoot"),
}
DEFAULT_PAIRS = {
    "bb_to_saddle_nose": ("bb_center", "saddle_nose"),
    "saddle_nose_to_handlebar": ("saddle_nose", "handlebar_reference"),
    "left_heel_to_forefoot": ("left_heel", "left_forefoot"),
    "right_heel_to_forefoot": ("right_heel", "right_forefoot"),
}


def number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def point(observation):
    if not isinstance(observation, dict):
        return None
    if observation.get("status") not in ("observed", "estimated"):
        return None
    xy = observation.get("xy_px")
    if not isinstance(xy, (list, tuple)) or len(xy) != 2 or not all(number(v) for v in xy):
        return None
    return tuple(xy)


def normalize(observations):
    rear = point(observations.get("rear_hub"))
    front = point(observations.get("front_hub"))
    if rear is None or front is None:
        raise ValueError("Both hubs must have usable coordinates")
    dx, dy = front[0] - rear[0], front[1] - rear[1]
    scale = math.hypot(dx, dy)
    if scale <= 1e-9 or abs(dx) / scale < 0.1:
        raise ValueError("Degenerate wheelbase or unsupported rotated view")
    ex = (dx / scale, dy / scale)
    ey = (-ex[1], ex[0])
    if ey[1] > 0:
        ey = (-ey[0], -ey[1])
    result = {}
    reference_estimated = any(observations[k].get("status") == "estimated" for k in ("rear_hub", "front_hub"))
    for name, obs in observations.items():
        xy = point(obs)
        status = obs.get("status", "missing") if isinstance(obs, dict) else "missing"
        entry = {"xy_percent": None, "status": status, "confidence": obs.get("confidence") if isinstance(obs, dict) else None}
        if xy is not None:
            v = (xy[0] - rear[0], xy[1] - rear[1])
            entry["xy_percent"] = [100 * (v[0] * axis[0] + v[1] * axis[1]) / scale for axis in (ex, ey)]
            entry["status"] = "estimated" if reference_estimated or status == "estimated" else "observed"
        elif status not in ("missing", "occluded"):
            entry["status"] = "missing"
        result[name] = entry
    return result


def angle(a, b, c):
    u = (a[0] - b[0], a[1] - b[1])
    v = (c[0] - b[0], c[1] - b[1])
    product = math.hypot(*u) * math.hypot(*v)
    if product <= 1e-12:
        return None
    cosine = max(-1.0, min(1.0, (u[0] * v[0] + u[1] * v[1]) / product))
    return math.degrees(math.acos(cosine))


def usable(points, names):
    return all(points.get(n, {}).get("xy_percent") is not None for n in names)


def derived_status(points, names):
    return "estimated" if any(points[n]["status"] == "estimated" for n in names) else "observed"


def measurements(points, pairs):
    angles = {}
    for side in ("left", "right"):
        angles[side] = {}
        for name, triple in ANGLE_POINTS.items():
            names = [side + "_" + n for n in triple]
            value = angle(*(points[n]["xy_percent"] for n in names)) if usable(points, names) else None
            angles[side][name] = {
                "value": value, "unit": "deg", "points": names,
                "status": derived_status(points, names) if value is not None else "missing",
                "uncertainty_deg": None,
            }
    distances = {}
    for name, names in pairs.items():
        if not isinstance(names, (list, tuple)) or len(names) != 2 or not all(isinstance(n, str) for n in names):
            raise ValueError("Distance pairs must contain two landmark names")
        entry = {"points": list(names), "distance": None, "dx": None, "dy": None, "unit": "percent_wheelbase", "status": "missing"}
        if usable(points, names):
            a, b = (points[n]["xy_percent"] for n in names)
            dx, dy = b[0] - a[0], b[1] - a[1]
            entry.update(distance=math.hypot(dx, dy), dx=dx, dy=dy, status=derived_status(points, names))
        distances[name] = entry
    return angles, distances


def phase(points, side):
    names = ("bb_center", "pedal_spindle_" + side)
    if not usable(points, names):
        return None
    bb, pedal = (points[n]["xy_percent"] for n in names)
    dx, dy = pedal[0] - bb[0], pedal[1] - bb[1]
    if math.hypot(dx, dy) <= 1e-9:
        return None
    return math.degrees(math.atan2(dx, dy)) % 360


def validate_input(data):
    if not isinstance(data, dict) or not isinstance(data.get("frames"), list):
        raise ValueError("Input must be an object containing a frames list")
    last_time = -math.inf
    for frame in data["frames"]:
        if not isinstance(frame, dict):
            raise ValueError("Each frame must be an object")
        t = frame.get("timestamp_s")
        if not number(t) or t < 0 or t <= last_time:
            raise ValueError("Frame timestamps must be finite, nonnegative and strictly increasing")
        last_time = t
        observations = frame.get("landmarks")
        if not isinstance(observations, dict):
            raise ValueError("Each frame requires a landmarks object")
        for obs in observations.values():
            if not isinstance(obs, dict) or obs.get("status") not in ("observed", "estimated", "missing", "occluded"):
                raise ValueError("Each landmark requires an explicit valid status")
            confidence = obs.get("confidence")
            if confidence is not None and (not number(confidence) or not 0 <= confidence <= 1):
                raise ValueError("Confidence must be null or a finite number in [0, 1]")
            if obs["status"] in ("observed", "estimated") and point(obs) is None:
                raise ValueError("Observed/estimated landmarks require two finite pixel coordinates")
            if obs["status"] in ("missing", "occluded") and obs.get("xy_px") is not None:
                raise ValueError("Missing/occluded landmarks must not carry coordinates")


def extract(data, side="right", tolerance_deg=5.0, max_gap_s=0.2):
    """Select observations within the first fully observed phase interval [0, 360)."""
    if side not in ("left", "right"):
        raise ValueError("Reference side must be left or right")
    if not number(tolerance_deg) or not 0 <= tolerance_deg < 15:
        raise ValueError("Tolerance must be in [0, 15) degrees to prevent frame reuse")
    if not number(max_gap_s) or max_gap_s <= 0:
        raise ValueError("Maximum observation gap must be positive")
    validate_input(data)
    samples = []
    rejected = 0
    for index, frame in enumerate(data["frames"]):
        try:
            points = normalize(frame["landmarks"])
        except ValueError:
            rejected += 1
            continue
        theta = phase(points, side)
        if theta is None:
            rejected += 1
            continue
        samples.append({"index": index, "frame": frame, "points": points, "phase": theta})
    if len(samples) < 3:
        raise ValueError("Too few usable frames")
    # Unwrap only forward, adequately sampled observations. Never bridge long gaps.
    crossings = []
    previous = None
    unwrapped = None
    for sample in samples:
        theta = sample["phase"]
        if previous is None:
            unwrapped = theta
            if theta == 0:
                crossings.append((0.0, sample["frame"]["timestamp_s"]))
        else:
            dt = sample["frame"]["timestamp_s"] - previous["frame"]["timestamp_s"]
            delta = (theta - previous["phase"] + 180) % 360 - 180
            if dt > max_gap_s:
                raise ValueError("Observation gap too long; cannot establish cycle continuity")
            if delta < 0 or delta >= 180:
                raise ValueError("Reverse/ambiguous phase progression; inspect tracking or increase frame rate")
            old = unwrapped
            unwrapped += delta
            boundary = (math.floor(old / 360) + 1) * 360
            if delta > 0 and unwrapped >= boundary:
                fraction = (boundary - old) / delta
                t = previous["frame"]["timestamp_s"] + fraction * dt
                crossings.append((float(boundary), t))
        sample["unwrapped"] = unwrapped
        previous = sample
        if len(crossings) >= 2:
            break
    if len(crossings) < 2:
        raise ValueError("No full cycle bounded by two top-dead-centre passages")
    (start, start_time), (end, end_time) = crossings[:2]
    candidates = [s for s in samples if "unwrapped" in s and start <= s["unwrapped"] < end]
    pairs = data.get("distance_pairs", DEFAULT_PAIRS)
    if not isinstance(pairs, dict):
        raise ValueError("distance_pairs must be an object")
    # Validate pair definitions even if every target is missing.
    measurements({}, pairs)
    states = []
    for target in STATES:
        state = {"target_phase_deg": target, "status": "missing", "frame_index": None,
                 "timestamp_s": None, "observed_phase_deg": None, "phase_error_deg": None,
                 "observations_px": {}, "landmarks": {}}
        nearest = min(candidates, key=lambda s: abs(s["unwrapped"] - start - target), default=None)
        if nearest is not None:
            error = nearest["unwrapped"] - start - target
            if abs(error) <= tolerance_deg + 1e-9:
                state.update(status="sampled", frame_index=nearest["frame"].get("frame_index", nearest["index"]),
                             timestamp_s=nearest["frame"]["timestamp_s"], observed_phase_deg=nearest["phase"],
                             phase_error_deg=error, observations_px=nearest["frame"]["landmarks"], landmarks=nearest["points"])
        state["angles"], state["distance_relations"] = measurements(state["landmarks"], pairs)
        states.append(state)
    return {
        "schema_version": "0.1.0", "producer": {"name": "schikatron", "version": __version__},
        "source": data.get("source", {}), "landmark_definitions": data.get("landmark_definitions", {}),
        "reference": {"geometry": "projected_2d", "origin": "rear_hub", "x_axis": "rear_hub_to_front_hub",
                      "y_axis": "perpendicular_toward_image_top", "scale": "wheelbase", "wheelbase_percent": 100,
                      "perspective_corrected": False},
        "cycle": {"states_deg": STATES.copy(), "reference_side": side, "zero": "pedal_above_bb_in_bike_frame",
                  "positive_direction": "top_toward_bike_front", "start_timestamp_s": start_time,
                  "end_timestamp_s": end_time, "boundary_method": "linear_phase_crossing",
                  "selection": "first_complete_single_cycle", "tolerance_deg": tolerance_deg,
                  "max_observation_gap_s": max_gap_s},
        "quality": {"input_frames": len(data["frames"]), "frames_without_reference_or_phase": rejected,
                    "sampled_states": sum(s["status"] == "sampled" for s in states),
                    "camera_calibration": "not_performed", "anatomical_accuracy": "not_validated"},
        "states": states,
    }
