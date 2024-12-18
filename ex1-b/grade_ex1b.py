# ex1b/grade_ex1b.py

import os
import zipfile
import tarfile
import subprocess
import shutil
import json
import re
import logging
from datetime import datetime

# Configuration Constants
# Determine the directory where the script resides
script_dir = os.path.dirname(os.path.abspath(__file__))

# Define absolute paths based on the script's directory
SUBMISSIONS_DIR = os.path.join(script_dir, 'submissions')
SUMMARY_DIR = os.path.join(script_dir, 'summary')
LOGS_DIR = os.path.join(script_dir, 'logs')
INPUT_DIR = os.path.join(script_dir, 'input')
GCC_COMMAND = 'gcc'  # Ensure GCC is installed and added to PATH
TIMEOUT_EXECUTION = 10  # seconds
MAX_COMMENT_LINES = 10  # Check first 10 lines for comments
MAX_README_LINES = 10   # Get first 10 lines from README

# Grading Rubric (Points Deducted)
POINTS = {
    'filename_correct': 5,
    'content_structure': 10,
    'compilation_errors_str_str': 10,
    'compilation_errors_count': 10,
    'compilation_errors_unique_str': 10,
    'compilation_errors_shell': 10,
    'compilation_warnings': 5,
    'execution_errors': 10,
    'output_capturing': 10,  # Changed from output_correct
    'child_processes': 10,
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

# Validate Filename
def correct_archive_filename(filename, expected_filename):
    """
    Validate if the filename matches expected patterns for zip or tgz archives.
    Example patterns: ex1b.zip, ex1b.tgz, ex1b.tar.gz
    Returns:
        str: 'zip' or 'tgz' if valid, else None
    """
    pattern = rf'^{re.escape(expected_filename)}\.(zip|tgz|tar\.gz)$'
    match = re.match(pattern, filename, re.IGNORECASE)
    if match:
        return match.group(1).lower()  # Returns the archive extension
    return None

# Extract Submission
def extract_submission(archive_path, extract_path, archive_type):
    try:
        if archive_type == 'zip':
            with zipfile.ZipFile(archive_path, 'r') as zip_ref:
                zip_ref.extractall(extract_path)
        elif archive_type in ['tgz', 'tar.gz']:
            with tarfile.open(archive_path, 'r:gz') as tar_ref:
                tar_ref.extractall(extract_path)
        else:
            logging.error(f"Unsupported archive type: {archive_type}")
            return False, f"Unsupported archive type: {archive_type}"
        
        extracted_files = os.listdir(extract_path)
        logging.info(f"Extracted files: {extracted_files}")
        return True, archive_type
    except Exception as e:
        logging.error(f"Failed to extract {archive_path}: {e}")
        return False, str(e)

# Check Content Structure
def check_content_structure(extract_path, expected_c_files):
    """
    Ensure that all expected .c files exist and README is present.
    """
    try:
        files = os.listdir(extract_path)
        logging.info(f"Extracted files: {files}")
        c_files = [f for f in files if f.endswith('.c')]
        # Accept 'README' or 'README.txt'
        readme_files = [f for f in files if f.lower() in ['readme', 'readme.txt']]

        readme_format_issue = False

        # Check if all expected .c files are present
        missing_c_files = [c for c in expected_c_files if c not in c_files]
        unexpected_c_files = [c for c in c_files if c not in expected_c_files]

        if missing_c_files:
            logging.error(f"Missing expected .c files: {missing_c_files}")
        if unexpected_c_files:
            logging.error(f"Unexpected .c files found: {unexpected_c_files}")

        # Check for README files
        if len(readme_files) != 1:
            logging.error(f"Expected 1 README file, found {len(readme_files)}: {readme_files}")
        else:
            if readme_files[0].lower() == 'readme':
                logging.info(f"Found correct README file: {readme_files[0]}")
            elif readme_files[0].lower() == 'readme.txt':
                readme_format_issue = True
                logging.warning(f"README file has incorrect format: {readme_files[0]} (expected 'README')")
            else:
                logging.error(f"Unexpected README filename: {readme_files[0]}")

        # Determine if content structure is okay
        content_ok = (
            len(missing_c_files) == 0 and
            len(unexpected_c_files) == 0 and
            len(readme_files) == 1
        )

        if content_ok:
            if readme_format_issue:
                # Content structure is okay, but README has wrong format
                logging.info(f"Content structure is correct, but README has incorrect format: {readme_files[0]}")
            else:
                logging.info(f"Content structure is correct with README: {readme_files[0]}")
            return True, c_files, readme_files[0], readme_format_issue
        else:
            return False, None, None, False
    except Exception as e:
        logging.error(f"Error checking content structure in {extract_path}: {e}")
        return False, None, None, False

# Compile Code
def compile_code(extract_path, c_file, output_name):
    compile_cmd = [GCC_COMMAND, '-Wall', '-o', output_name, c_file]
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

# Execute Shell Commands
def execute_shell_commands(extract_path, shell_program, commands):
    """
    Executes a list of commands via the shell program (ex1ba.exe).
    
    :param extract_path: Directory where the shell program resides
    :param shell_program: Name of the shell executable
    :param commands: List of commands to send to the shell
    :return: (returncode, stdout, stderr)
    """
    if not shell_program.lower().endswith('.exe'):
        shell_program += '.exe'
    
    shell_path = os.path.join(extract_path, shell_program)
    
    execute_cmd = [shell_path]
    
    try:
        process = subprocess.Popen(
            execute_cmd,
            cwd=extract_path,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True
        )
        
        # Combine commands into a single string with newline separators
        input_str = '\n'.join(commands) + '\n'
        
        stdout, stderr = process.communicate(input=input_str, timeout=TIMEOUT_EXECUTION)
        logging.info(f"Executed {shell_program} with return code {process.returncode}")
        return process.returncode, stdout.strip(), stderr.strip()
    except subprocess.TimeoutExpired:
        logging.error(f"Shell execution timed out in {extract_path}: {shell_program}")
        process.kill()
        return -1, "", "Shell execution timed out."
    except Exception as e:
        logging.error(f"Shell execution failed in {extract_path}: {shell_program} - {e}")
        return -1, "", str(e)

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
    Expected folder name format: <name>_<id>_assignsubmission_file
    Returns:
        tuple: (student_id, student_name)
    """
    try:
        # Example folder name: אדיר כהן_1736405_assignsubmission_file
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
def process_submission(student_id, student_name, submission_folder, shell_commands, expected_c_files):
    log = {
        'Student ID': student_id,
        'Student Name': student_name,
        'Submission Folder': submission_folder,
        'Filename Correct': True,
        'Archive Type': "",  # Added to log the type of archive
        'Content Structure': True,
        'Compilation': {
            'str_str.c': True,
            'count.c': True,
            'unique_str.c': True,
            'ex1ba.c': True  # shell
        },
        'Compilation Warnings': {
            'str_str.c': [],
            'count.c': [],
            'unique_str.c': [],
            'ex1ba.c': []
        },
        'Compilation Errors': {
            'str_str.c': [],
            'count.c': [],
            'unique_str.c': [],
            'ex1ba.c': []
        },
        'Execution Errors': [],
        'Output Capturing': {
            'str_str': "",
            'count': "",
            'unique_str': "",
            'shell': ""
        },
        'Comments Present': {
            'str_str.c': True,
            'count.c': True,
            'unique_str.c': True,
            'ex1ba.c': True  # shell
        },
        'README First 10 Lines': [],
        'Program Stderr': {
            'str_str.c': "",
            'count.c': "",
            'unique_str.c': "",
            'ex1ba.c': ""
        },
        'Actual Output': {
            'str_str': "", 
            'count': "",
            'unique_str': "",
            'shell': ""
        },
        'Issues': [],
        'Points Deducted': 0,
        'Final Score': TOTAL_POINTS
    }

    deductions = 0

    # Path to the submission folder
    submission_path = os.path.join(SUBMISSIONS_DIR, submission_folder)

    # Search for the expected archive file within the submission folder
    archive_files = [f for f in os.listdir(submission_path) if f.lower().endswith(('.zip', '.tgz', '.tar.gz'))]

    if not archive_files:
        logging.error(f"No supported archive file found in {submission_folder}")
        log['Filename Correct'] = False
        log['Issues'].append("Missing ex1b.zip/tgz file.")
        deductions += POINTS['filename_correct']
        log['Points Deducted'] += POINTS['filename_correct']
        log['Final Score'] = TOTAL_POINTS - deductions
        return log
    elif len(archive_files) > 1:
        logging.error(f"Multiple archive files found in {submission_folder}: {archive_files}")
        log['Filename Correct'] = False
        log['Issues'].append("Multiple archive files found.")
        deductions += POINTS['filename_correct'] * 2  # Deduct double points for multiple files
        log['Points Deducted'] += POINTS['filename_correct'] * 2
        log['Final Score'] = TOTAL_POINTS - deductions
        return log
    else:
        archive_file = archive_files[0]
        # Validate the filename and determine archive type
        archive_type = correct_archive_filename(archive_file, 'ex1b')
        if not archive_type:
            logging.error(f"Incorrect or unsupported filename '{archive_file}' in {submission_folder}")
            log['Filename Correct'] = False
            log['Issues'].append(f"Incorrect or unsupported filename: {archive_file}")
            deductions += POINTS['filename_correct']
            log['Points Deducted'] += POINTS['filename_correct']
        else:
            logging.info(f"Found correct archive file: {archive_file} ({archive_type.upper()}) in {submission_folder}")
            log['Archive Type'] = archive_type.upper()

    # Prepare Extraction Path (extract directly into submission folder)
    # No need to sanitize student_name as we're extracting into the submission folder
    extract_path = submission_path

    # Path to the archive file
    archive_path = os.path.join(submission_path, archive_file)

    # Extract Submission
    if archive_type:
        success, extraction_result = extract_submission(archive_path, extract_path, archive_type)
        if not success:
            log['Content Structure'] = False
            log['Issues'].append(f"Extraction failed: {extraction_result}")
            deductions += POINTS['content_structure']
            log['Points Deducted'] += POINTS['content_structure']
            # Deduct points for all other categories as extraction failed
            for c_file in log['Compilation']:
                log['Compilation'][c_file] = False
                log['Compilation Errors'][c_file].append("Compilation skipped due to extraction failure.")
            deductions += (POINTS['compilation_errors_str_str'] + 
                           POINTS['compilation_errors_count'] + 
                           POINTS['compilation_errors_unique_str'] + 
                           POINTS['compilation_errors_shell'])
            log['Execution Errors'].append("Execution skipped due to extraction failure.")
            deductions += POINTS['execution_errors']
            log['Output Capturing'] = {k: "" for k in log['Output Capturing']}
            log['Final Score'] = TOTAL_POINTS - deductions
            return log
    else:
        # If archive_type is None due to incorrect filename
        extraction_result = "Unsupported archive type."
        success = False

    # Content Structure Check
    if success and archive_type:
        content_ok, c_files, readme_file, readme_format_issue = check_content_structure(extract_path, expected_c_files)
        if not content_ok:
            log['Content Structure'] = False
            log['Issues'].append("Incorrect content structure.")
            deductions += POINTS['content_structure']
    else:
        content_ok, c_files, readme_file, readme_format_issue = False, None, None, False

    # Initialize readme_path to None to prevent UnboundLocalError
    readme_path = None

    if content_ok:
        logging.info(f"Processing .c files and {readme_file} for student {student_id} - {student_name}")
        readme_path = os.path.join(extract_path, readme_file)
        logging.info(f"Files: {c_files}, {readme_path}")

        # Compile Each .c File
        for c_file in c_files:
            c_file_path = os.path.join(extract_path, c_file)
            if c_file == 'str_str.c':
                output_name = 'str_str.exe'
            elif c_file == 'count.c':
                output_name = 'count.exe'
            elif c_file == 'unique_str.c':
                output_name = 'unique_str.exe'
            elif c_file == 'ex1ba.c':
                output_name = 'ex1ba.exe'  # shell
            else:
                output_name = os.path.splitext(c_file)[0] + '.exe'
            compile_result = compile_code(extract_path, c_file, output_name)
            returncode, warnings, errors = compile_result

            # Initialize compilation logs
            log['Compilation Warnings'][c_file] = warnings
            log['Compilation Errors'][c_file] = errors

            if returncode != 0 or errors:
                log['Compilation'][c_file] = False
                log['Issues'].append(f"Compilation failed for {c_file}.")
                if c_file == 'str_str.c':
                    deductions += POINTS['compilation_errors_str_str']
                    log['Points Deducted'] += POINTS['compilation_errors_str_str']
                elif c_file == 'count.c':
                    deductions += POINTS['compilation_errors_count']
                    log['Points Deducted'] += POINTS['compilation_errors_count']
                elif c_file == 'unique_str.c':
                    deductions += POINTS['compilation_errors_unique_str']
                    log['Points Deducted'] += POINTS['compilation_errors_unique_str']
                elif c_file == 'ex1ba.c':
                    deductions += POINTS['compilation_errors_shell']
                    log['Points Deducted'] += POINTS['compilation_errors_shell']
                else:
                    # For unexpected .c files
                    deductions += POINTS['compilation_errors_shell']
                    log['Points Deducted'] += POINTS['compilation_errors_shell']
            else:
                if warnings:
                    log['Compilation Warnings'][c_file] = warnings
                    deductions += POINTS['compilation_warnings']

        # Handle README format issue
        if readme_format_issue:
            log['Issues'].append("README has incorrect format (should be 'README' without extension).")
            deductions += POINTS['readme_correct']

        # If compilations succeeded for all .c files, proceed
        if all(log['Compilation'].values()):
            # Read shell commands from shell_commands parameter
            if not shell_commands:
                log['Execution Errors'].append("No shell commands provided.")
                deductions += POINTS['execution_errors']
            else:
                # Execute shell.exe with the provided commands
                logging.info("Executing shell.exe with commands")
                exec_returncode, actual_output_shell, exec_stderr_shell = execute_shell_commands(
                    extract_path,
                    'ex1ba.exe',
                    shell_commands
                )
                log['Program Stderr']['ex1ba.c'] = exec_stderr_shell
                log['Output Capturing']['shell'] = actual_output_shell

                if exec_returncode != 0:
                    log['Execution Errors'].append("shell.exe execution failed or timed out.")
                    deductions += POINTS['execution_errors']
                else:
                    # Capture and log the actual outputs without validation
                    log['Actual Output']['shell'] = actual_output_shell

    # Check Comments and Extract First 10 Lines for Each .c File
    for c_file in expected_c_files:
        c_file_path = os.path.join(extract_path, c_file)
        comments_present, first_10_lines = check_comments(c_file_path)
        log['Comments Present'][c_file] = comments_present
        if not comments_present:
            log['Issues'].append(f"No comments found in the first {MAX_COMMENT_LINES} lines of {c_file}.")
            deductions += POINTS['comments_present']
    # Store README first 10 lines
    log['README First 10 Lines'] = []
    if readme_path and os.path.exists(readme_path):
        try:
            with open(readme_path, 'r', encoding='utf-8') as f:
                readme_lines = [f.readline().rstrip('\n') for _ in range(MAX_README_LINES)]
            log['README First 10 Lines'] = readme_lines
            # Optionally, add logic to validate the README content here
        except Exception as e:
            logging.error(f"Failed to read README file {readme_path}: {e}")
            log['Issues'].append("Failed to read README file.")
            deductions += POINTS['readme_correct']
    else:
        logging.error("README path is not set or does not exist.")
        log['Issues'].append("README file is missing.")
        deductions += POINTS['readme_correct']

    # Calculate Final Score
    log['Points Deducted'] = deductions
    log['Final Score'] = TOTAL_POINTS - deductions

    # Note: Removed cleanup to keep extracted content in submission folder

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
    logging.info("Starting grading process for Exercise 1b.")

    # Ensure necessary directories exist
    os.makedirs(SUMMARY_DIR, exist_ok=True)
    os.makedirs(LOGS_DIR, exist_ok=True)
    os.makedirs('workdir', exist_ok=True)  # If not needed anymore, you can remove or repurpose it

    summary_file = os.path.join(SUMMARY_DIR, 'summary_ex1b.json')

    # Read shell commands from input_ex2.txt
    try:
        with open(os.path.join(INPUT_DIR, 'input_ex2.txt'), 'r', encoding='utf-8') as f:
            shell_commands = f.read().strip().splitlines()
        if not shell_commands:
            raise ValueError("input_ex2.txt must contain at least one command.")
        logging.info("Loaded shell commands from input_ex2.txt.")
    except Exception as e:
        logging.error(f"Failed to read input_ex2.txt: {e}")
        shell_commands = ['exit']  # Default to exit if reading fails

    # Initialize summary list
    summary = []

    # Define expected .c files for ex1b
    expected_c_files_ex1b = ['str_str.c', 'count.c', 'unique_str.c', 'ex1ba.c']  # ex1ba.c is the shell

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
        log = process_submission(
            student_id=student_id,
            student_name=student_name,
            submission_folder=submission_folder,
            shell_commands=shell_commands,
            expected_c_files=expected_c_files_ex1b
        )
        summary.append(log)
        logging.info(f"Finished processing: {submission_folder} | Final Score: {log['Final Score']}")

    # Generate JSON Summary
    generate_json_summary(summary, summary_file)

    logging.info("Grading complete for Exercise 1b.")

if __name__ == "__main__":
    main()
