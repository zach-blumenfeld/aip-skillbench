No earthquake in `{earthquakes_path}` falls inside plate {plate_code} ({plate_name}): {n_in_plate} of {n_earthquakes} events are within its polygon in `{plates_path}`.

Before concluding that the plate truly has no events, rule out an input problem:

1. Confirm `{plate}` names the plate the task asks about (codes and names come from the plates file's `Code` / `PlateName` columns; the Pacific plate is `PA`).
2. Spot-check the earthquake file: point coordinates must be `[longitude, latitude, depth]` (GeoJSON order); swapped lon/lat puts every event in the wrong place.
3. Do not widen the filter (buffers, nearest plate, polygon outline) to manufacture a result — the task asks for events within the plate itself.

If an input problem is found, say exactly what it is and how to rerun the procedure with corrected inputs. If the inputs are correct, the honest answer is that there is no qualifying earthquake: do not invent one and do not write `{output_path}`.

Respond with `diagnosis`: one short paragraph stating which case applies and the evidence.
