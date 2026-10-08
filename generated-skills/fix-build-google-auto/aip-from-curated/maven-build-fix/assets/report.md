Write the final report for the Maven build fix in {project_dir}.

Outcome: **{build_outcome}** after {round} build round(s). Last command: `{build_command}` (JDK `{jdk}`), log {build_log_path}.

If the outcome is `passed`: confirm the log shows BUILD SUCCESS for every reactor module (`diagnosis.reactor_summary`) and that the command carries no skip flags the original lacked (`run_notes`). Run `git -C {project_dir} diff --stat` and list each changed file with a one-line reason. Mention `pom_findings` you left unfixed as follow-ups, not as changes.

If the outcome is `exhausted`: the round limit was reached. State the remaining failure (`failure_category`, `diagnosis.failing_goal`, first error lines), what was tried (`changes_made`), and the most likely next fix. Leave the working tree in its best state; do not revert changes that fixed earlier errors.

Return JSON: {{"summary": "<root cause, files changed and why, final build command and result>", "changes_made": [...]}}
