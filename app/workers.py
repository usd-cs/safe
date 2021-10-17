import os
import subprocess
import datetime
import json
import requests
from glob import glob
from flask import url_for
from rq import get_current_job

import app
safe_app = app.create_app()

def get_filenames(source_files, source_dir='.'):
    all_filenames = []
    for filename in source_files:
        if '*' in filename:
            # if this contains a wildcard, use glob to get list of
            # matching files
            pathname = os.path.join(source_dir, filename)
            all_filenames += [os.path.split(f)[1] for f in glob(pathname)]
        else:
            all_filenames.append(filename)

    return all_filenames

def testing_successful(job, conn, runner_output, *args, **kwargs):
    """
    Callback function when testing job completes successfully.
    """
    job_id = job.get_id()

    print(f"SUCCESS: {job_id}")
    #print(f"result: {runner_output}")

    with safe_app.app_context():
        notification_url = url_for('notify.update_results', 
                                   job_id=job_id, 
                                   _external=True,
                                   _scheme=safe_app.config['PREFERRED_URL_SCHEME'])

    server_response = requests.post(notification_url, json=runner_output)
    print("Server Response:", server_response.text)


def testing_failed(job, conn, exception_type, exception_instance, traceback):
    """
    Callback function when testing job fails.
    """
    job_id = job.get_id()

    print(f"FAILED: {job_id}")
    print(f"\t{exception_instance}")

    failure_info = { "error": str(exception_instance) }

    with safe_app.app_context():
        notification_url = url_for('notify.remove_failed',
                                   job_id=job_id,
                                   _external=True,
                                   _scheme=safe_app.config['PREFERRED_URL_SCHEME'])

    server_response = requests.post(notification_url, json=failure_info)
    print("Server Response:", server_response.text)


def run_test(git_server, repo_base_dir, repo_name, test_code_dir, test_command,
                timeout_length, source_files, tester_files, group_members):
    print(f"Handling request for {repo_name}")

    if not os.path.exists(test_code_dir):
        raise RuntimeError(f"Testing code directory does not exist: {repo_base_dir}")
    elif not os.path.exists(repo_base_dir):
        raise RuntimeError(f"Repo base directory does not exist: {repo_base_dir}")

    repo_location = os.path.join(repo_base_dir, repo_name)

    # import here to avoid making safe app container image require git
    from git import Repo

    # check if we need to clone the repository first
    if os.path.exists(repo_location):
        # repo directory already exists, so just do a pull
        print("\tExisting repository found. Pulling...")

        os.chdir(repo_location)
        repo = Repo(os.getcwd())
        origin = repo.remote('origin')
        origin.pull()

    else:
        # repo dir doesn't exist, so clone repository
        print("\tExisting repository not found. Cloning...")

        repo = Repo.clone_from(f"git@{git_server}:{repo_name}", repo_location)
        os.chdir(repo_location)

    # get time, author, and message for latest commit
    latest_commit = repo.commit('master')

    submission_time = str(latest_commit.committed_datetime)
    author = latest_commit.author
    commit_author = f"{author.name} ({author.email})"
    commit_comment = latest_commit.message.strip()

    print("\tSetting up testing directory...")
    job = get_current_job()
    testing_dir = os.path.join(repo_location, "safe_testing", job.id)
    os.makedirs(testing_dir)

    for filename in tester_files:
        result = subprocess.call(["cp", os.path.join(test_code_dir, filename), testing_dir])
        if result != 0:
            raise RuntimeError(f"Could not copy testing file: {filename}")

    files_under_test = get_filenames(source_files)

    cp_args = ["cp"] + files_under_test
    cp_args.append(testing_dir)
    if subprocess.call(cp_args) != 0:
        raise RuntimeError(f"Could not copy {', '.join(files_under_test)}: {repo_name}")

    # replace special tokens in test command with proper values
    final_test_command = []
    for cmd_arg in test_command:
        if cmd_arg == '%g':
            final_test_command += group_members
        else:
            final_test_command.append(cmd_arg)

    os.chdir(testing_dir)
    print(f"\tRunning test command: {' '.join(final_test_command)}...")
    try:
        os.putenv('PYTHONDONTWRITEBYTECODE', 'TRUE')
        result = subprocess.run(final_test_command, capture_output=True, timeout=timeout_length)

        # TODO: if result.returncode isn't 0, raise an exception

        output_text = result.stdout
        error_text = result.stderr
        print(f"\tGrader finished with status code {result.returncode}")

    except subprocess.TimeoutExpired as e:
        output_text = e.stdout
        error_text = e.stderr
        print(f"\tGrader timed out after {e.timeout} seconds")

    else:
        runner_output = {}
        runner_output['author'] = commit_author
        runner_output['submission_time'] = submission_time
        runner_output['commit_comment'] = commit_comment
        runner_output['results_time'] = str(datetime.datetime.now())

        with open('results.json', 'r') as results_file:
            runner_output['results'] = json.load(results_file)

    finally:
        os.unsetenv('PYTHONDONTWRITEBYTECODE')

        with open("stdout.txt", "wb") as stdout_file, open("stderr.txt", "wb") as stderr_file:
            if output_text is not None:
                stdout_file.write(output_text)
            if error_text is not None:
                stderr_file.write(error_text)

        return runner_output

