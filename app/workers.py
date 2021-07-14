import sys
import os
import subprocess
import datetime
import json
import requests
from dateutil import parser
from collections import namedtuple

TesterOutput = namedtuple('TesterOutput', ['commit_time', 'commit_comment', 'commit_author', 'data'])

mock_json_data = """
[
    {
        "section": "Part 1: Yada yada yada",
        "status": "PASS",
        "summary": "Requirement 1",
        "detail": "All tests passed for this requirement."
    },
    {
        "section": "Part 1: Yada yada yada",
        "status": "FAIL",
        "summary": "Requirement 2",
        "detail": "One or more tests did not pass for this requirement."
    },
    {
        "section": "Part 2: Boop",
        "status": "PASS",
        "summary": "Requirement 1",
        "detail": "All tests passed for this requirement."
    }
]
"""

#def testing_successful(job, conn, runner_output, *args, **kwargs):

def testing_successful(job, conn, runner_output, *args, **kwargs):
    """
    Callback function when testing job completes successfully.
    """
    job_id = job.get_id()

    print(f"SUCCESS: {job_id}")
    print(f"result: {runner_output}")

    requests.post(f"http://localhost:5000/done/{job_id}", json=runner_output)


def testing_failed(job, conn, exception_type, exception_instance, traceback):
    """
    Callback function when testing job fails.
    """
    print(f"FAILED: {job.get_id()}")
    print(f"\t{exception_type}")


def run_test(repo_base_dir, repo_name, test_code_dir, test_command, timeout_length, source_files):
    print(f"Handling request for {repo_name}")

    repo_location = os.path.join(repo_base_dir, repo_name)

    # check if we need to clone the repository first
    needs_pulled = True
    if not os.path.exists(repo_location):
        print("\tExisting repository not found. Cloning...")
        os.chdir(f"{repo_base_dir}")
        result = subprocess.call(["git", "clone", "git@code:" + repo_name])

        if result != 0:
            print(f"Could not clone: {repo_name}")
            return

        needs_pulled = False # fresh clone so don't need to pull later

    os.chdir(repo_location)

    # Pull latest changes, if necessary
    if needs_pulled:
        print("\tPulling from repository...")
        if subprocess.call(["git", "pull"]) != 0:
            print(f"Could not pull: {repo_name}")
            return

    # check if the tester code directory exists, creating it if
    # necessary
    if not os.path.exists("tester"):
        print("\tSetting up tester directory...")
        result = subprocess.call(["cp", "-r", test_code_dir, "tester"])
        if result != 0:
            print(f"Could not copy tester code: {repo_name}")
            return

    files_under_test = []
    for filename in source_files:
        if '*' in filename:
            # if this contains a wildcard, use glob to get list of
            # matching files
            from glob import glob
            files_under_test += glob(filename)
        else:
            files_under_test.append(filename)


    cp_args = ["cp"] + files_under_test + ["tester/"]
    if subprocess.call(cp_args) != 0:
        print(f"Could not copy {', '.join(files_under_test)}: {repo_name}")
        return

    os.chdir("tester/")
    print("\tRunning grader...")
    try:
        result = subprocess.run(test_command, capture_output=True, timeout=timeout_length)
        output_text = result.stdout
        error_text = result.stderr
        print(f"\tGrader finished with status code {result.returncode}")

    except subprocess.TimeoutExpired as e:
        output_text = e.stdout
        error_text = e.stderr
        print(f"\tGrader timed out after {e.timeout} seconds")

    with open("stdout.txt", "wb") as stdout_file, open("stderr.txt", "wb") as stderr_file:
        if output_text is not None:
            stdout_file.write(output_text)
        if error_text is not None:
            stderr_file.write(error_text)


    runner_output = {}
    runner_output['author'] = "Sat Garcia (sat@sandiego.edu)"
    runner_output['submission_time'] = "Tue Jul 13 08:25:09 2021 -0700"
    runner_output['commit_comment'] = "We're finally done"
    runner_output['results_time'] = str(datetime.datetime.now())
    runner_output['results'] = json.loads(mock_json_data)

    print("DONEZO!")

    return runner_output
    #return TesterOutput(commit_time, commit_comment, commit_author, mock_json_data)


