No DBSCAN setting reached a mean F1 > 0.5, so the Pareto frontier is empty and {output_csv}
holds only the header `F1,delta,min_samples,epsilon,shape_weight`. Under the task's rules that
is the correct output. Do not lower the threshold or add rows. Confirm that the empty result
is real and not a pipeline bug, then explain it.

Grid summary:
{grid_summary}

Data report:
{data_report}

Checks:
1. Read `{output_csv}` and confirm it holds exactly the header line.
2. Compare best_f1 with 0.5. Just below (above about 0.4) points to data that is hard to
   cluster. Near 0 points to a structural problem: check that
   expert_images_without_citsci is not most of expert_images (a key mismatch), and that
   expert_x_range/expert_y_range sit on the same pixel scale as citsci_x_range/citsci_y_range.
   Expert points should fall inside the citizen-science range; an offset or a different scale
   means no centroid gets within 100 px.
3. If the grid was customized (n_combinations differs from 847), note that the standard
   grid might reach the threshold.

Answer with `empty_diagnosis`: the likely cause, each check and its result, and confirmation
that the CSV holds only the header.
