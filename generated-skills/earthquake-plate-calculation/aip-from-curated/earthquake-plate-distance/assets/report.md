# Report the computation result

Write a short, direct answer to the user's original request using the
computed values below. Lead with the headline number (distance in km,
rounded to two decimals). When the metric picked a specific earthquake,
name it by USGS id, magnitude, and place. Do not add caveats,
methodology notes, or restate the question.

## Original request

{user_request}

## Computed values

- plate: {plate_name} ({plate_code})
- metric: {metric}
- earthquakes inside plate: {n_earthquakes_in_plate}
- distance (km): {distance_km}
- earthquake picked: {earthquake}

## Pre-written summary (use as the backbone of your answer)

{summary}

Return a JSON object with a single key `answer` whose value is the final
answer text (1–3 sentences). No prose outside the JSON.
