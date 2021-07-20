import os
import subprocess
import datetime
import json
import requests
import git

def testing_successful(job, conn, runner_output, *args, **kwargs):
    """
    Callback function when testing job completes successfully.
    """
    job_id = job.get_id()

    print(f"SUCCESS: {job_id}")
    #print(f"result: {runner_output}")

    # FIXME: URL needs customized based on app's config
    server_response = requests.post(f"http://localhost:5000/notify/success/{job_id}", 
                                    json=runner_output)
    print("Server Response:", server_response.text)


def testing_failed(job, conn, exception_type, exception_instance, traceback):
    """
    Callback function when testing job fails.
    """
    job_id = job.get_id()

    print(f"FAILED: {job_id}")
    print(f"\t{exception_instance}")

    failure_info = { "error": str(exception_instance) }

    # FIXME: URL needs customized based on app's config
    server_response = requests.post(f"http://localhost:5000/notify/failed/{job_id}",
                                    json=failure_info)
    print("Server Response:", server_response.text)


def run_test(git_server, repo_base_dir, repo_name, test_code_dir, test_command, timeout_length, source_files):
    print(f"Handling request for {repo_name}")

    repo_location = os.path.join(repo_base_dir, repo_name)

    # check if we need to clone the repository first
    needs_pulled = True
    if not os.path.exists(repo_location):
        print("\tExisting repository not found. Cloning...")
        os.chdir(f"{repo_base_dir}")
        result = subprocess.call(["git", "clone", f"git@{git_server}:{repo_name}"])

        if result != 0:
            raise RuntimeError(f"Could not clone: {repo_name}")

        needs_pulled = False # fresh clone so don't need to pull later

    os.chdir(repo_location)

    # Pull latest changes, if necessary
    if needs_pulled:
        print("\tPulling from repository...")
        if subprocess.call(["git", "pull"]) != 0:
            raise RuntimeError(f"Could not pull: {repo_name}")

    # get time, author, and message for latest commit
    repo = git.Repo(os.getcwd())
    latest_commit = repo.commit('master')

    submission_time = str(latest_commit.committed_datetime)
    author = latest_commit.author
    commit_author = f"{author.name} ({author.email})"
    commit_comment = latest_commit.message.strip()

    # check if the tester code directory exists, creating it if
    # necessary
    if not os.path.exists("tester"):
        print("\tSetting up tester directory...")
        result = subprocess.call(["cp", "-r", test_code_dir, "tester"])
        if result != 0:
            raise RuntimeError(f"Could not copy tester code: {repo_name}")

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
        raise RuntimeError(f"Could not copy {', '.join(files_under_test)}: {repo_name}")

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
    runner_output['author'] = commit_author
    runner_output['submission_time'] = submission_time
    runner_output['commit_comment'] = commit_comment
    runner_output['results_time'] = str(datetime.datetime.now())

    with open('results.json', 'r') as results_file:
        runner_output['results'] = json.load(results_file)

    return runner_output

