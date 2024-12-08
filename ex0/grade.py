# grade.py

import os
import tarfile
import subprocess
import shutil
import json
import re
import logging
from datetime import datetime
from difflib import ndiff

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
    'compilation_errors': 60,
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
            universal_newlines=True,
            check=True
        )
        version_output = result.stdout.splitlines()[0]
        # Adjust the regex pattern based on your specific GCC version output
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
    Example pattern: ex0.tgz
    Modify the regex as per actual naming conventions.
    """
    pattern = r'^ex0\.tgz$'
    return re.match(pattern, filename) is not None

# Extract Submission
def extract_submission(tgz_path, extract_path):
    try:
        with tarfile.open(tgz_path, 'r:gz') as tar:
            tar.extractall(path=extract_path)
        extracted_files = os.listdir(extract_path)
        logging.info(f"Extracted files: {extracted_files}")
        return True, ""
    except Exception as e:
        logging.error(f"Failed to extract {tgz_path}: {e}")
        return False, str(e)

# Check Content Structure
def check_content_structure(extract_path):
    """
    Ensure exactly one .c file and one README file exist.
    Allows README or README.txt but logs if the README has a .txt extension.
    """
    try:
        files = os.listdir(extract_path)
        logging.info(f"Extracted files: {files}")
        c_files = [f for f in files if f.endswith('.c')]
        # Accept 'README' or 'README.txt'
        readme_files = [f for f in files if f.lower() in ['readme', 'readme.txt']]

        readme_format_issue = False
        correct_readme_filename = False

        if len(readme_files) != 1:
            logging.error(f"Expected 1 README file, found {len(readme_files)}: {readme_files}")
        else:
            if readme_files[0].lower() == 'readme':
                correct_readme_filename = True
            elif readme_files[0].lower() == 'readme.txt':
                readme_format_issue = True
                logging.warning(f"README file has incorrect format: {readme_files[0]} (expected 'README')")
        
        if len(c_files) != 1:
            logging.error(f"Expected 1 .c file, found {len(c_files)}: {c_files}")
        
        content_ok = (len(c_files) == 1 and len(readme_files) == 1)
        if content_ok:
            if readme_format_issue:
                # Content structure is okay, but README has wrong format
                logging.info(f"Content structure is correct, but README has incorrect format: {readme_files[0]}")
            else:
                logging.info(f"Content structure is correct with README: {readme_files[0]}")
            return True, c_files[0], readme_files[0], readme_format_issue
        else:
            return False, None, None, False
    except Exception as e:
        logging.error(f"Error checking content structure in {extract_path}: {e}")
        return False, None, None, False

# Compile Code
def compile_code(extract_path, c_file):
    compile_cmd = [GCC_COMMAND, '-Wall', '-o', 'program', c_file]
    try:
        result = subprocess.run(
            compile_cmd,
            cwd=extract_path,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True
        )
        compile_output = result.stderr.strip()
        logging.info(f"Compiled {c_file} with return code {result.returncode}")
        
        # Separate warnings and errors
        warnings = []
        errors = []
        for line in compile_output.split('\n'):
            if 'warning:' in line.lower():
                warnings.append(line)
            elif 'error:' in line.lower():
                errors.append(line)
        
        return result.returncode, warnings, errors
    except Exception as e:
        logging.error(f"Compilation failed for {c_file}: {e}")
        return -1, [], [str(e)]

# Run Valgrind
def run_valgrind(extract_path):
    input_file_path = os.path.join('/grading', INPUT_FILE)  # Ensure this is correct
    valgrind_cmd = [
        'valgrind',
        '--leak-check=full',
        '--error-exitcode=1',
        '--log-file=valgrind.log',
        './program',
        input_file_path  # Pass the input file path as an argument
    ]
    try:
        result = subprocess.run(
            valgrind_cmd,
            cwd=extract_path,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            timeout=TIMEOUT_VALGRIND
        )
        # Read valgrind log
        valgrind_log_path = os.path.join(extract_path, 'valgrind.log')
        if os.path.exists(valgrind_log_path):
            with open(valgrind_log_path, 'r', encoding='utf-8') as f:
                valgrind_output = f.read()
        else:
            valgrind_output = "Valgrind log not found."
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
    input_file_path = os.path.join('/grading', INPUT_FILE)
    logging.info(f"Input file given to program: {input_file_path}")
    execute_cmd = ['./program', input_file_path]
    try:
        result = subprocess.run(
            execute_cmd,
            cwd=extract_path,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
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
    """
    Generate a human-readable diff between actual and expected outputs using ndiff.
    """
    expected_lines = [line.rstrip() for line in expected_output.strip().splitlines()]
    actual_lines = [line.rstrip() for line in actual_output.strip().splitlines()]
    diff = '\n'.join(ndiff(expected_lines, actual_lines))
    return diff

# Check Comments in .c File and Extract First 10 Lines
def check_comments(c_file_path):
    try:
        with open(c_file_path, 'r', encoding='utf-8') as f:
            lines = [f.readline().rstrip('\n') for _ in range(MAX_COMMENT_LINES)]
        comments_found = any(re.match(r'^\s*(//|/\*)', line) for line in lines if line)
        if comments_found:
            logging.info(f"Found comment in {c_file_path}")
        else:
            logging.warning(f"No comments found in the first {MAX_COMMENT_LINES} lines of {c_file_path}")
        return comments_found, lines
    except Exception as e:
        logging.error(f"Failed to check comments in {c_file_path}: {e}")
        return False, []

# Extract Student ID and Name from Folder Name
def extract_student_info(folder_name):
    """
    Extract student ID and name from the folder name.
    Expected folder name format: <some_id>_name(hebrew)_assignsubmission_file
    Returns:
        tuple: (student_id, student_name)
    """
    try:
        # Example folder name: מוחמד פראח_1718693_assignsubmission_file
        pattern = r'^(.*?)_(\d+)_assignsubmission_file$'
        match = re.match(pattern, folder_name)
        if match:
            student_name = match.group(1).strip()
            student_id = match.group(2).strip()
            return student_id, student_name
        else:
            logging.warning(f"Folder name '{folder_name}' does not match the expected pattern.")
            return "Unknown_ID", "Unknown_Name"
    except Exception as e:
        logging.error(f"Error extracting student info from folder name '{folder_name}': {e}")
        return "Unknown_ID", "Unknown_Name"

# Process Each Submission
def process_submission(student_id, student_name, submission_folder, expected_output):
    log = {
        'Student ID': student_id,
        'Student Name': student_name,
        'Submission Folder': submission_folder,
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
        'Program Stderr': "",
        'Actual Output': "", 
        'Diff': "",
        'Issues': [],
        'Points Deducted': 0,
        'Final Score': TOTAL_POINTS
    }

    deductions = 0

    # Path to the submission folder
    submission_path = os.path.join(SUBMISSIONS_DIR, submission_folder)

    # Search for ex0.tgz within the submission folder
    tgz_files = [f for f in os.listdir(submission_path) if f.endswith('.tgz')]
    
    if not tgz_files:
        logging.error(f"No .tgz file found in {submission_folder}")
        log['Filename Correct'] = False
        log['Issues'].append("Missing ex0.tgz file.")
        deductions += POINTS['filename_correct']
        log['Points Deducted'] += POINTS['filename_correct']
        log['Final Score'] = TOTAL_POINTS - deductions
        return log
    elif len(tgz_files) > 1:
        logging.error(f"Multiple .tgz files found in {submission_folder}: {tgz_files}")
        log['Filename Correct'] = False
        log['Issues'].append("Multiple .tgz files found.")
        deductions += POINTS['filename_correct'] * 2  # Deduct double points for multiple files
        log['Points Deducted'] += POINTS['filename_correct'] * 2
        log['Final Score'] = TOTAL_POINTS - deductions
        return log
    else:
        tgz_file = tgz_files[0]
        # Validate the filename
        if not correct_filename(tgz_file):
            logging.error(f"Incorrect filename '{tgz_file}' in {submission_folder}")
            log['Filename Correct'] = False
            log['Issues'].append(f"Incorrect filename: {tgz_file}")
            deductions += POINTS['filename_correct']
            log['Points Deducted'] += POINTS['filename_correct']
        else:
            logging.info(f"Found correct .tgz file: {tgz_file} in {submission_folder}")

    # Prepare Extraction Path
    extract_path = os.path.join('/grading', 'workdir', f"{student_id}_{student_name}")
    os.makedirs(extract_path, exist_ok=True)

    # Path to the tgz file
    tgz_path = os.path.join(submission_path, tgz_file)

    # Extract Submission
    success, message = extract_submission(tgz_path, extract_path)
    if not success:
        log['Content Structure'] = False
        log['Issues'].append(f"Extraction failed: {message}")
        deductions += POINTS['content_structure']
        log['Points Deducted'] += POINTS['content_structure']
        log['Compilation'] = False
        deductions += POINTS['compilation_errors']
        log['Points Deducted'] += POINTS['compilation_errors']
        log['Valgrind'] = False
        deductions += POINTS['valgrind']
        log['Points Deducted'] += POINTS['valgrind']
        log['Output Correct'] = False
        deductions += POINTS['output_correct']
        log['Points Deducted'] += POINTS['output_correct']
        log['Comments Present'] = False
        deductions += POINTS['comments_present']
        log['Points Deducted'] += POINTS['comments_present']
        log['README First 10 Lines'] = []
        deductions += POINTS['readme_correct']
        log['Points Deducted'] += POINTS['readme_correct']
        shutil.rmtree(extract_path, ignore_errors=True)
        log['Final Score'] = TOTAL_POINTS - deductions
        return log

    # Content Structure Check
    content_ok, c_file, readme_file, readme_format_issue = check_content_structure(extract_path)
    if not content_ok:
        log['Content Structure'] = False
        log['Issues'].append("Incorrect content structure.")
        deductions += POINTS['content_structure']

    if content_ok:
        logging.info(f"Processing {c_file} and {readme_file} for student {student_id} - {student_name}")
        c_file_path = os.path.join(extract_path, c_file)
        readme_path = os.path.join(extract_path, readme_file)
        logging.info(f"Paths: {c_file_path}, {readme_path}")

        # Compile Code
        returncode, warnings, errors = compile_code(extract_path, c_file)
        log['Compilation Warnings'] = warnings
        log['Compilation Errors'] = errors
        if returncode != 0 or errors:
            log['Compilation'] = False
            log['Issues'].append("Compilation failed.")
            deductions += POINTS['compilation_errors']
        else:
            if warnings:
                log['Compilation Warnings'] = warnings
                deductions += POINTS['compilation_warnings']

        # Handle README format issue
        if readme_format_issue:
            log['Issues'].append("README has incorrect format (should be 'README' without extension).")
            deductions += POINTS['readme_correct']

        # If compilation succeeded, proceed
        if log['Compilation']:
            # Run Valgrind
            valgrind_returncode, valgrind_output = run_valgrind(extract_path)
            log['Valgrind Output'] = valgrind_output
            if valgrind_returncode != 0:
                log['Valgrind'] = False
                log['Issues'].append("Valgrind detected memory leaks or errors.")
                deductions += POINTS['valgrind']

            # Execute Program
            exec_returncode, actual_output, exec_stderr = execute_program(extract_path)
            log['Actual Output'] = actual_output  # Record actual output
            log['Program Stderr'] = exec_stderr  # Optionally record stderr
            if exec_returncode != 0:
                log['Output Correct'] = False
                log['Issues'].append("Program execution failed or timed out.")
                deductions += POINTS['output_correct']
                actual_output += f"\n{exec_stderr}" if exec_stderr else ""

            # Compare Output
            if not compare_output(actual_output, expected_output):
                log['Output Correct'] = False
                log['Issues'].append("Program output does not match expected output.")
                deductions += POINTS['output_correct']
                # Generate diff
                diff = generate_diff(actual_output, expected_output)
                log['Diff'] = diff
       
        # Check Comments and Extract First 10 Lines
        comments_present, first_10_lines = check_comments(c_file_path)
        log['Comments Present'] = comments_present
        if not comments_present:
            log['Issues'].append("No comments found in the first 10 lines of the .c file.")
            deductions += POINTS['comments_present']
        log['README First 10 Lines'] = []
        try:
            with open(readme_path, 'r', encoding='utf-8') as f:
                readme_lines = [f.readline().rstrip('\n') for _ in range(MAX_README_LINES)]
            log['README First 10 Lines'] = readme_lines
            # Optionally, add logic to validate the README content here
        except Exception as e:
            logging.error(f"Failed to read README file {readme_path}: {e}")
            log['Issues'].append("Failed to read README file.")
            deductions += POINTS['readme_correct']

    # Calculate Final Score
    log['Points Deducted'] = deductions
    log['Final Score'] = TOTAL_POINTS - deductions

    # Clean up
    shutil.rmtree(extract_path, ignore_errors=True)

    return log

# Generate JSON Summary
def generate_json_summary(summary, output_path):
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=4, ensure_ascii=False)
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
        with open(EXPECTED_OUTPUT_FILE, 'r', encoding='utf-8') as f:
            expected_output = f.read()
        logging.info("Loaded expected output.")
    except Exception as e:
        logging.error(f"Failed to read expected output file: {e}")
        return

    # Initialize summary list
    summary = []

    # Iterate over each submission folder in submissions
    for submission_folder in os.listdir(SUBMISSIONS_DIR):
        submission_path = os.path.join(SUBMISSIONS_DIR, submission_folder)
        if not os.path.isdir(submission_path):
            logging.warning(f"Skipping non-directory item in submissions: {submission_folder}")
            continue  # Skip non-directory items

        logging.info(f"Processing submission folder: {submission_folder}")

        # Extract student information from folder name
        student_id, student_name = extract_student_info(submission_folder)
        logging.info(f"Extracted Student ID: {student_id}, Student Name: {student_name}")

        # Process the submission
        log = process_submission(student_id, student_name, submission_folder, expected_output)
        summary.append(log)
        logging.info(f"Finished processing: {submission_folder} | Final Score: {log['Final Score']}")

    # Generate JSON Summary
    generate_json_summary(summary, summary_file)

    logging.info("Grading complete.")

if __name__ == "__main__":
    main()
