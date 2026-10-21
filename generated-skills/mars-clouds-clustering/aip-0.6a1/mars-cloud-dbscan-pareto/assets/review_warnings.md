The data check before the DBSCAN grid search raised warnings. Decide, for each one, whether
the task's scoring rules already handle it (benign) or whether it means the run is pointed at
the wrong data (blocking).

Data report:
{data_report}

How each warning is handled by the scoring:
- Expert images with no citizen-science points: benign. They still count, scoring F1 = 0.0
  and delta = NaN. Blocking only when they are more than half the expert images, which
  usually means the wrong file pairing or a mismatched image key.
- Citizen-science images not in the expert file: benign. Images are looped over from the
  expert file, so these are ignored.
- Dropped rows (missing or non-numeric x/y, or an empty file_rad): benign when they are a
  small share of the rows. Blocking when most rows were dropped (a wrong column or a broken file).
- Image keys with a variant suffix (_log, _contrast_stretch_0_75/_0_85): blocking when the two
  files disagree on whether the suffix is present, because the same image would then fail to
  join. Benign when both files use the same keys.

If any warning is blocking, do not continue: stop the run, report the problem, and restart
`inspect-data` with corrected inputs. Never edit the input data files. Otherwise answer with
`data_review`: one line per warning (benign or blocking, with the reason) and a final line
saying "proceed".
