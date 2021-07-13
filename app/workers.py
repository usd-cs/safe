import os
import subprocess

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


