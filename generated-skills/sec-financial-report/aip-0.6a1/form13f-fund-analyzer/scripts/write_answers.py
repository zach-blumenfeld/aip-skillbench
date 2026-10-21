"""Write the answers object to the task's JSON file and check its value types.

stdin state: answers (object), answers_path (string)
stdout: answers_written, answer_warnings
"""
import json
import os

from f13common import emit, fail, read_state


def check(key, v, warnings):
    if v is None or v == "" or v == []:
        warnings.append(f"{key}: empty answer")
    elif isinstance(v, str):
        try:
            float(v.replace(",", ""))
            warnings.append(f"{key}: number written as a string ({v!r}); write a JSON number")
        except ValueError:
            pass
    elif isinstance(v, list):
        for i, x in enumerate(v):
            if not isinstance(x, (str, int, float)) or isinstance(x, bool):
                warnings.append(f"{key}[{i}]: expected a string or number, got {type(x).__name__}")
        if len(set(map(str, v))) != len(v):
            warnings.append(f"{key}: duplicate entries")


def main():
    s = read_state()
    answers = s.get("answers")
    path = s.get("answers_path")
    if not isinstance(answers, dict) or not answers:
        fail("answers must be a non-empty JSON object")
    if not path:
        fail("answers_path is required")
    out = {}
    warnings = []
    for k, v in answers.items():
        if isinstance(v, float) and v.is_integer():
            v = int(v)  # 13F VALUE sums are whole dollars
        check(k, v, warnings)
        out[k] = v
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w") as f:
        json.dump(out, f, indent=4)
        f.write("\n")
    with open(path) as f:
        json.load(f)
    emit({"answers_written": os.path.abspath(path), "answer_warnings": warnings})


if __name__ == "__main__":
    main()
