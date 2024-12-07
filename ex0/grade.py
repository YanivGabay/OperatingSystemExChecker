# grade.py

import os
import tarfile
import subprocess
import shutil
import json
import re
import logging
from datetime import datetime
from difflib import unified_diff

# Configuration Constants
SUBMISSIONS_DIR = 'submissions'
SUMMARY_DIR = 'summary'
LOGS_DIR = 'logs'
INPUT_FILE = 'input/input.txt'
EXPECTED_OUTPUT_FILE = 'expected_output/expected_output.txt'
GCC_COMMAND = 'gcc'  # Ensure this points to GCC 8.5.0-22 in your Docker environment
TIMEOUT_EXECUTION = 5  # seconds
TIMEOUT_VALGRIND = 10  # seconds
MAX_COMMENT_LINES = 10  # Check first 10 lines for comments
MAX_README_LINES = 10   # Get first 10 lines from README

# Grading Rubric (Points Deducted)
POINTS = {
    'filename_correct': 5,
    'content_structure': 10,
    'compilation_errors': 10,
    'compilation_warnings': 5,
    'valgrind': 10,
    'output_correct': 10,
    'comments_present': 5,
    'readme_correct': 5
}
TOTAL_POINTS = 100

# Initialize Logging
def setup_logging():
    os.makedirs(LOGS_DIR, exist_ok=True)
    log_filename = os.path.join(LOGS_DIR, f'grading_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log')
    logging.basicConfig(
        filename=log_filename,
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    # Also log to console
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    formatter = logging.Formatter('%(levelname)s - %(message)s')
    console.setFormatter(formatter)
    logging.getLogger('').addHandler(console)

# Verify GCC Version
def verify_gcc_version():
    try:
        result = subprocess.run(
            [GCC_COMMAND, '--version'],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True
        )
        version_output = result.stdout.splitlines()[0]
        expected_version_pattern = r'^gcc \(GCC\) 8\.5\.0 .*Red Hat 8\.5\.0-22'
        if re.match(expected_version_pattern, version_output):
            logging.info(f"GCC version verified: {version_output}")
            return True
        else:
            logging.error(f"Incorrect GCC version: {version_output}")
            return False
    except subprocess.CalledProcessError as e:
        logging.error(f"Failed to run GCC: {e}")
        return False
    except Exception as e:
        logging.error(f"Error verifying GCC version: {e}")
        return False

# Validate Filename
def correct_filename(filename):
    """
    Define the correct filename pattern.
    Example pattern: studentID_assignment.tgz
    Modify the regex as per actual naming conventions.
    """
    # Example: ex0.tgz
    pattern = r'^ex0\.tgz$'
    return re.match(pattern, filename) is not None

# Extract Submission
def extract_submission(tgz_path, extract_path):
    try:
        with tarfile.open(tgz_path, 'r:gz') as tar:
            tar.extractall(path=extract_path)
        logging.info(f"Extracted {tgz_path} to {extract_path}")
        return True, ""
    except Exception as e:
        logging.error(f"Failed to extract {tgz_path}: {e}")
        return False, str(e)

# Check Content Structure
def check_content_structure(extract_path):
    """
    Ensure exactly one .c file and one README file exist.
    """
    try:
        files = os.listdir(extract_path)
        c_files = [f for f in files if f.endswith('.c')]
        readme_files = [f for f in files if f.lower() == 'readme']
        if len(c_files) != 1 or len(readme_files) != 1 or len(files) != 2:
            logging.warning(f"Content structure invalid in {extract_path}. Files found: {files}")
            return False, c_files, readme_files
        return True, c_files[0], readme_files[0]
    except Exception as e:
        logging.error(f"Error checking content structure in {extract_path}: {e}")
        return False, [], []

# Compile Code
def compile_code(extract_path, c_file):
    compile_cmd = [GCC_COMMAND, '-Wall', '-o', 'program', c_file]
    try:
        result = subprocess.run(
            compile_cmd,
            cwd=extract_path,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        compile_output = result.stderr.strip()
        logging.info(f"Compiled {c_file} with return code {result.returncode}")
        
        # Separate warnings and errors
        warnings = []
        errors = []
        for line in compile_output.split('\n'):
            if 'warning:' in line:
                warnings.append(line)
            elif 'error:' in line:
                errors.append(line)
        
        return result.returncode, warnings, errors
    except Exception as e:
        logging.error(f"Compilation failed for {c_file}: {e}")
        return -1, [], [str(e)]

# Run Valgrind
def run_valgrind(extract_path):
    valgrind_cmd = [
        'valgrind',
        '--leak-check=full',
        '--error-exitcode=1',
        '--log-file=valgrind.log',
        './program'
    ]
    try:
        with open(INPUT_FILE, 'r') as infile:
            result = subprocess.run(
                valgrind_cmd,
                cwd=extract_path,
                stdin=infile,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=TIMEOUT_VALGRIND
            )
        # Read valgrind log
        with open(os.path.join(extract_path, 'valgrind.log'), 'r') as f:
            valgrind_output = f.read()
        logging.info(f"Ran Valgrind with return code {result.returncode}")
        return result.returncode, valgrind_output.strip()
    except subprocess.TimeoutExpired:
        logging.error(f"Valgrind timed out in {extract_path}")
        return -1, "Valgrind timed out."
    except Exception as e:
        logging.error(f"Valgrind failed in {extract_path}: {e}")
        return -1, str(e)

# Execute Program
def execute_program(extract_path):
    execute_cmd = ['./program']
    try:
        with open(INPUT_FILE, 'r') as infile:
            result = subprocess.run(
                execute_cmd,
                cwd=extract_path,
                stdin=infile,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=TIMEOUT_EXECUTION
            )
        logging.info(f"Executed program with return code {result.returncode}")
        return result.returncode, result.stdout.strip(), result.stderr.strip()
    except subprocess.TimeoutExpired:
        logging.error(f"Program execution timed out in {extract_path}")
        return -1, "", "Execution timed out."
    except Exception as e:
        logging.error(f"Program execution failed in {extract_path}: {e}")
        return -1, "", str(e)

# Compare Output
def compare_output(actual_output, expected_output):
    """
    Compare actual and expected outputs line by line after normalizing whitespace.
    
    Returns:
        bool: True if outputs match exactly, False otherwise.
    """
    # Normalize line endings and strip trailing whitespaces
    actual_lines = [line.rstrip() for line in actual_output.strip().splitlines()]
    expected_lines = [line.rstrip() for line in expected_output.strip().splitlines()]
    
    if actual_lines == expected_lines:
        return True
    else:
        return False

# Generate Diff
def generate_diff(actual_output, expected_output):
    expected_lines = [line.rstrip() for line in expected_output.strip().splitlines()]
    actual_lines = [line.rstrip() for line in actual_output.strip().splitlines()]
    diff = '\n'.join(unified_diff(expected_lines, actual_lines, fromfile='expected_output', tofile='actual_output'))
    return diff

# Check Comments in .c File and Extract First 10 Lines
def check_comments(c_file_path):
    try:
        with open(c_file_path, 'r') as f:
            lines = [f.readline().rstrip('\n') for _ in range(MAX_COMMENT_LINES)]
        comments_found = any(re.match(r'^\s*(//|/\*)', line) for line in lines if line)
        if comments_found:
            logging.info(f"Found comment in {c_file_path}")
        else:
            logging.warning(f"No comments found in the first {MAX_COMMENT_LINES} lines of {c_file_path}")
        # Since Python 3.6 doesn't support assignment expressions, we split the return
        return comments_found, lines
    except Exception as e:
        logging.error(f"Failed to check comments in {c_file_path}: {e}")
        return False, []

# Process Each Submission
def process_submission(tgz_file, expected_output):
    log = {
        'Filename': tgz_file,
        'Filename Correct': True,
        'Content Structure': True,
        'Compilation': True,
        'Compilation Warnings': [],
        'Compilation Errors': [],
        'Valgrind': True,
        'Valgrind Output': "",
        'Output Correct': True,
        'Comments Present': True,
        'README First 10 Lines': [],
        'Diff': "",
        'Points Deducted': 0,
        'Final Score': TOTAL_POINTS
    }

    deductions = 0

    # Filename Check
    if not correct_filename(tgz_file):
        log['Filename Correct'] = False
        deductions += POINTS['filename_correct']
        logging.info(f"Filename incorrect: {tgz_file}")

    # Prepare Extraction Path
    submission_id = os.path.splitext(tgz_file)[0]
    extract_path = os.path.join('/grading', 'workdir', submission_id)
    os.makedirs(extract_path, exist_ok=True)

    # Extract Submission
    tgz_path = os.path.join(SUBMISSIONS_DIR, tgz_file)
    success, message = extract_submission(tgz_path, extract_path)
    if not success:
        log['Content Structure'] = False
        deductions += POINTS['content_structure']
        log['Compilation'] = False
        deductions += POINTS['compilation_errors']
        log['Valgrind'] = False
        deductions += POINTS['valgrind']
        log['Output Correct'] = False
        deductions += POINTS['output_correct']
        log['Comments Present'] = False
        deductions += POINTS['comments_present']
        log['README First 10 Lines'] = []
        deductions += POINTS['readme_correct']
        log['Points Deducted'] = deductions
        log['Final Score'] = TOTAL_POINTS - deductions
        shutil.rmtree(extract_path)
        return log

    # Content Structure Check
    content_ok, c_files, readme_files = check_content_structure(extract_path)
    if not content_ok:
        log['Content Structure'] = False
        deductions += POINTS['content_structure']

    if content_ok:
        c_file = c_files[0]
        readme_file = readme_files[0]
        c_file_path = os.path.join(extract_path, c_file)
        readme_path = os.path.join(extract_path, readme_file)

        # Compile Code
        returncode, warnings, errors = compile_code(extract_path, c_file)
        log['Compilation Warnings'] = warnings
        log['Compilation Errors'] = errors
        if returncode != 0 or errors:
            log['Compilation'] = False
            deductions += POINTS['compilation_errors']
        else:
            if warnings:
                log['Compilation Warnings'] = warnings
                deductions += POINTS['compilation_warnings']

        # If compilation succeeded, proceed
        if log['Compilation']:
            # Run Valgrind
            valgrind_returncode, valgrind_output = run_valgrind(extract_path)
            log['Valgrind Output'] = valgrind_output
            if valgrind_returncode != 0:
                log['Valgrind'] = False
                deductions += POINTS['valgrind']

            # Execute Program
            exec_returncode, actual_output, exec_stderr = execute_program(extract_path)
            if exec_returncode != 0:
                log['Output Correct'] = False
                deductions += POINTS['output_correct']
                actual_output += f"\n{exec_stderr}" if exec_stderr else ""

            # Compare Output
            if not compare_output(actual_output, expected_output):
                log['Output Correct'] = False
                deductions += POINTS['output_correct']
                # Generate diff
                diff = generate_diff(actual_output, expected_output)
                log['Diff'] = diff

        # Check Comments and Extract First 10 Lines
        comments_present, first_10_lines = check_comments(c_file_path)
        log['Comments Present'] = comments_present
        if not comments_present:
            deductions += POINTS['comments_present']
        log['README First 10 Lines'] = []
        try:
            with open(readme_path, 'r') as f:
                readme_lines = [f.readline().rstrip('\n') for _ in range(MAX_README_LINES)]
            log['README First 10 Lines'] = readme_lines
            # Optionally, you can add logic here to validate names within these lines
        except Exception as e:
            logging.error(f"Failed to read README file {readme_path}: {e}")
            deductions += POINTS['readme_correct']

    # Calculate Final Score
    log['Points Deducted'] = deductions
    log['Final Score'] = TOTAL_POINTS - deductions

    # Clean up
    shutil.rmtree(extract_path)

    return log

# Generate JSON Summary
def generate_json_summary(summary, output_path):
    try:
        with open(output_path, 'w') as f:
            json.dump(summary, f, indent=4)
        logging.info(f"JSON summary generated at {output_path}")
    except Exception as e:
        logging.error(f"Failed to write JSON summary: {e}")

# Main Function
def main():
    setup_logging()
    logging.info("Starting grading process.")

    # Verify GCC version
    if not verify_gcc_version():
        logging.error("GCC version mismatch. Aborting grading process.")
        return

    # Ensure necessary directories exist
    os.makedirs(SUMMARY_DIR, exist_ok=True)
    os.makedirs(LOGS_DIR, exist_ok=True)
    os.makedirs('/grading/workdir', exist_ok=True)  # Ensure workdir exists inside Docker

    summary_file = os.path.join(SUMMARY_DIR, 'summary.json')

    # Read expected output
    try:
        with open(EXPECTED_OUTPUT_FILE, 'r') as f:
            expected_output = f.read()
        logging.info("Loaded expected output.")
    except Exception as e:
        logging.error(f"Failed to read expected output file: {e}")
        return

    # Initialize summary list
    summary = []

    # Iterate over each .tgz file in submissions
    for tgz_file in os.listdir(SUBMISSIONS_DIR):
        if not tgz_file.endswith('.tgz'):
            logging.warning(f"Skipping non-tgz file: {tgz_file}")
            continue  # Skip non-tgz files

        logging.info(f"Processing submission: {tgz_file}")
        log = process_submission(tgz_file, expected_output)
        summary.append(log)
        logging.info(f"Finished processing: {tgz_file} | Final Score: {log['Final Score']}")

    # Generate JSON Summary
    generate_json_summary(summary, summary_file)

    logging.info("Grading complete.")

if __name__ == "__main__":
    main()
