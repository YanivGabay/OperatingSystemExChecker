# ex1/grade.py

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
INPUT_DIR = 'input'
GCC_COMMAND = 'gcc'  # Ensure this points to GCC 8.5.0-22 in your Docker environment
TIMEOUT_EXECUTION = 10  # seconds
TIMEOUT_VALGRIND = 15  # seconds
MAX_COMMENT_LINES = 10  # Check first 10 lines for comments
MAX_README_LINES = 10   # Get first 10 lines from README

# Grading Rubric (Points Deducted)
POINTS = {
    'filename_correct': 5,
    'content_structure': 10,
    'compilation_errors_ex1a': 10,
    'compilation_errors_ex1b': 10,
    'compilation_errors_extra': 10,
    'compilation_warnings': 5,
    'valgrind': 10,
    'output_correct_ex1a': 10,
    'output_correct_ex1b': 10,
    'child_processes': 10,
    'command_execution': 10,
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
def correct_filename(filename, expected_filename):
    """
    Define the correct filename pattern.
    Example pattern: ex1.tgz
    Modify the regex as per actual naming conventions.
    """
    pattern = rf'^{expected_filename}\.tgz$'
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
def check_content_structure(extract_path, expected_c_files, extra_c_files):
    """
    Ensure that all expected .c files exist.
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
        unexpected_c_files = [c for c in c_files if c not in expected_c_files and c not in extra_c_files]

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

# Run Valgrind
def run_valgrind(extract_path, program, args=None):
    """
    Runs Valgrind on a specified program with given arguments.
    
    :param extract_path: Directory where the program resides
    :param program: Executable to run with Valgrind
    :param args: List of arguments to pass to the executable
    :return: (returncode, valgrind_output)
    """
    if args is None:
        args = []
    valgrind_cmd = [
        'valgrind',
        '--leak-check=full',
        '--error-exitcode=1',
        '--log-file=valgrind.log',
        os.path.join(extract_path, program)
    ] + args
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
        logging.info(f"Ran Valgrind on {program} with return code {result.returncode}")
        return result.returncode, valgrind_output.strip()
    except subprocess.TimeoutExpired:
        logging.error(f"Valgrind timed out on {program} in {extract_path}")
        return -1, "Valgrind timed out."
    except Exception as e:
        logging.error(f"Valgrind failed on {program} in {extract_path}: {e}")
        return -1, str(e)

# Execute Program
def execute_program(extract_path, program, args=None, input_commands=None):
    """
    Executes a program with optional arguments and input commands.
    
    :param extract_path: Path where the program resides
    :param program: Executable to run
    :param args: List of arguments to pass to the executable
    :param input_commands: List of commands to send to the program's stdin
    :return: (returncode, stdout, stderr)
    """
    if args is None:
        args = []
    if input_commands is None:
        input_commands = []

    execute_cmd = [os.path.join(extract_path, program)] + args

    try:
        process = subprocess.Popen(
            execute_cmd,
            cwd=extract_path,
            stdin=subprocess.PIPE if input_commands else None,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True
        )
        
        # Send input commands if any
        if input_commands:
            input_str = '\n'.join(input_commands) + '\n'
        else:
            input_str = ''

        stdout, stderr = process.communicate(input=input_str, timeout=TIMEOUT_EXECUTION)
        logging.info(f"Executed {program} with return code {process.returncode}")
        return process.returncode, stdout.strip(), stderr.strip()
    except subprocess.TimeoutExpired:
        logging.error(f"Program execution timed out in {extract_path}: {program}")
        process.kill()
        return -1, "", "Execution timed out."
    except Exception as e:
        logging.error(f"Program execution failed in {extract_path}: {program} - {e}")
        return -1, "", str(e)

# Compare Output (Not used for ex1 since no expected output)
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

# Generate Diff (Optional, since no expected output)
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
    Expected folder name format: <name>_<id>_assignsubmission_file
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
def process_submission(student_id, student_name, submission_folder, commands_to_send, expected_c_files, extra_c_files):
    log = {
        'Student ID': student_id,
        'Student Name': student_name,
        'Submission Folder': submission_folder,
        'Filename Correct': True,
        'Content Structure': True,
        'Compilation': {
            'ex1a.c': True,
            'ex1b.c': True,
            'char_in_str.c': True,
            'pid.c': True,
            'unique_str.c': True
        },
        'Compilation Warnings': {
            'ex1a.c': [],
            'ex1b.c': [],
            'char_in_str.c': [],
            'pid.c': [],
            'unique_str.c': []
        },
        'Compilation Errors': {
            'ex1a.c': [],
            'ex1b.c': [],
            'char_in_str.c': [],
            'pid.c': [],
            'unique_str.c': []
        },
        'Valgrind': True,
        'Valgrind Output': "",
        'Output Correct': {
            'ex1a': True,
            'ex1b': True
        },
        'Comments Present': {
            'ex1a.c': True,
            'ex1b.c': True,
            'char_in_str.c': True,
            'pid.c': True,
            'unique_str.c': True
        },
        'README First 10 Lines': [],
        'Program Stderr': {
            'ex1a.c': "",
            'ex1b.c': "",
            'char_in_str.c': "",
            'pid.c': "",
            'unique_str.c': ""
        },
        'Actual Output': {
            'ex1a': "", 
            'ex1b': ""
        },
        'Command Execution Results': {
            './pid': None,
            './char_in_str': None,
            './unique_str': None
        },
        'Issues': [],
        'Points Deducted': 0,
        'Final Score': TOTAL_POINTS
    }

    deductions = 0

    # Path to the submission folder
    submission_path = os.path.join(SUBMISSIONS_DIR, submission_folder)

    # Search for the expected .tgz file within the submission folder
    tgz_files = [f for f in os.listdir(submission_path) if f.endswith('.tgz')]

    if not tgz_files:
        logging.error(f"No .tgz file found in {submission_folder}")
        log['Filename Correct'] = False
        log['Issues'].append("Missing ex1.tgz file.")
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
        if not correct_filename(tgz_file, 'ex1'):
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
        # Deduct points for all other categories as extraction failed
        for c_file in log['Compilation']:
            log['Compilation'][c_file] = False
            log['Compilation Errors'][c_file].append("Compilation skipped due to extraction failure.")
        deductions += POINTS['compilation_errors_ex1a'] + POINTS['compilation_errors_ex1b'] + POINTS['compilation_errors_extra']
        log['Valgrind'] = False
        deductions += POINTS['valgrind']
        log['Points Deducted'] += POINTS['valgrind']
        log['Output Correct']['ex1a'] = False
        log['Output Correct']['ex1b'] = False
        deductions += POINTS['output_correct_ex1a'] + POINTS['output_correct_ex1b']
        log['Points Deducted'] += POINTS['output_correct_ex1a'] + POINTS['output_correct_ex1b']
        log['Comments Present'] = {k: False for k in log['Comments Present']}
        deductions += POINTS['comments_present'] * len(log['Comments Present'])
        log['Points Deducted'] += POINTS['comments_present'] * len(log['Comments Present'])
        log['README First 10 Lines'] = []
        deductions += POINTS['readme_correct']
        log['Points Deducted'] += POINTS['readme_correct']
        shutil.rmtree(extract_path, ignore_errors=True)
        log['Final Score'] = TOTAL_POINTS - deductions
        return log

    # Content Structure Check
    content_ok, c_files, readme_file, readme_format_issue = check_content_structure(extract_path, expected_c_files, extra_c_files)
    if not content_ok:
        log['Content Structure'] = False
        log['Issues'].append("Incorrect content structure.")
        deductions += POINTS['content_structure']

    if content_ok:
        logging.info(f"Processing .c files and {readme_file} for student {student_id} - {student_name}")
        readme_path = os.path.join(extract_path, readme_file)
        logging.info(f"Paths: {c_files}, {readme_path}")

        # Compile Each .c File
        for c_file in c_files:
            c_file_path = os.path.join(extract_path, c_file)
            if c_file == 'ex1a.c':
                output_name = 'ex1a'
            elif c_file == 'ex1b.c':
                output_name = 'ex1b'
            else:
                output_name = os.path.splitext(c_file)[0]
            compile_result = compile_code(extract_path, c_file, output_name)
            returncode, warnings, errors = compile_result

            # Initialize compilation logs
            log['Compilation Warnings'][c_file] = warnings
            log['Compilation Errors'][c_file] = errors

            if returncode != 0 or errors:
                log['Compilation'][c_file] = False
                log['Issues'].append(f"Compilation failed for {c_file}.")
                if c_file == 'ex1a.c':
                    deductions += POINTS['compilation_errors_ex1a']
                    log['Points Deducted'] += POINTS['compilation_errors_ex1a']
                elif c_file == 'ex1b.c':
                    deductions += POINTS['compilation_errors_ex1b']
                    log['Points Deducted'] += POINTS['compilation_errors_ex1b']
                else:
                    # For extra .c files
                    deductions += POINTS['compilation_errors_extra']
                    log['Points Deducted'] += POINTS['compilation_errors_extra']
            else:
                if warnings:
                    log['Compilation Warnings'][c_file] = warnings
                    deductions += POINTS['compilation_warnings']

        # Handle README format issue
        if readme_format_issue:
            log['Issues'].append("README has incorrect format (should be 'README' without extension).")
            deductions += POINTS['readme_correct']

        # If compilations succeeded for ex1a.c and ex1b.c, proceed
        if log['Compilation']['ex1a.c'] and log['Compilation']['ex1b.c']:
            # Run Valgrind on ex1a.c (compiled as 'ex1a')
            logging.info("Running Valgrind on ex1a")
            valgrind_returncode, valgrind_output = run_valgrind(extract_path, 'ex1a', args=['output_report.txt', '42'])
            log['Valgrind Output'] = valgrind_output
            if valgrind_returncode != 0:
                log['Valgrind'] = False
                log['Issues'].append("Valgrind detected memory leaks or errors in ex1a.c.")
                deductions += POINTS['valgrind']

            # Execute ex1a.c with two arguments: output filename and seed
            logging.info("Executing ex1a.c with arguments")
            try:
                # Parse the first line of commands_to_send
                output_filename, seed = commands_to_send[0].split()
                exec_returncode, actual_output_ex1a, exec_stderr_ex1a = execute_program(
                    extract_path,
                    'ex1a',
                    args=[output_filename, seed]
                )
                log['Program Stderr']['ex1a.c'] = exec_stderr_ex1a
                log['Actual Output']['ex1a'] = actual_output_ex1a
                if exec_returncode != 0:
                    log['Output Correct']['ex1a'] = False
                    log['Issues'].append("ex1a.c execution failed or timed out.")
                    deductions += POINTS['output_correct_ex1a']
                else:
                    # Read the output file generated by ex1a.c
                    output_file_path = os.path.join(extract_path, output_filename)
                    try:
                        with open(output_file_path, 'r') as f:
                            ex1a_output = f.read().strip()
                        log['Actual Output']['ex1a'] = ex1a_output
                        # Since no expected output, we store the actual output
                    except Exception as e:
                        logging.error(f"Failed to read output file {output_file_path}: {e}")
                        log['Output Correct']['ex1a'] = False
                        log['Issues'].append("Failed to read ex1a.c output file.")
                        deductions += POINTS['output_correct_ex1a']
            except Exception as e:
                logging.error(f"Error processing commands_to_send for ex1a.c: {e}")
                log['Output Correct']['ex1a'] = False
                log['Issues'].append("Invalid input for ex1a.c.")
                deductions += POINTS['output_correct_ex1a']

            # Execute ex1b.c with commands from commands_to_send
            logging.info("Executing ex1b.c with commands")
            try:
                # The rest of the commands are for ex1b.c
                ex1b_commands = commands_to_send[1:]
                # Ensure unique_str commands have arguments concatenated appropriately
                # Since students do not use quotes, we need to adjust unique_str commands to pass a single argument
                adjusted_ex1b_commands = []
                for cmd in ex1b_commands:
                    tokens = cmd.strip().split()
                    if not tokens:
                        continue
                    command = tokens[0]
                    args = tokens[1:]
                    if command in ['./unique_str', 'unique_str']:
                        # Combine all arguments into a single string
                        if args:
                            combined_arg = ' '.join(args)
                            adjusted_ex1b_commands.append(f"{command} {combined_arg}")
                        else:
                            adjusted_ex1b_commands.append(command)
                    else:
                        # For other commands, keep as is
                        adjusted_ex1b_commands.append(cmd)
                
                exec_returncode_b, actual_output_ex1b, exec_stderr_ex1b = execute_program(
                    extract_path,
                    'ex1b',
                    args=[],
                    input_commands=adjusted_ex1b_commands
                )
                log['Program Stderr']['ex1b.c'] = exec_stderr_ex1b
                log['Actual Output']['ex1b'] = actual_output_ex1b
                if exec_returncode_b != 0:
                    log['Output Correct']['ex1b'] = False
                    log['Issues'].append("ex1b.c execution failed or timed out.")
                    deductions += POINTS['output_correct_ex1b']
                else:
                    log['Output Correct']['ex1b'] = True
                    # No expected output to compare
            except Exception as e:
                logging.error(f"Error processing commands_to_send for ex1b.c: {e}")
                log['Output Correct']['ex1b'] = False
                log['Issues'].append("Invalid input for ex1b.c.")
                deductions += POINTS['output_correct_ex1b']

            # Check for Leftover Child Processes
            logging.info("Checking for leftover child processes")
            try:
                # Get list of processes before execution
                before_ps = subprocess.check_output(['ps', '-ef'], universal_newlines=True)
                # Execute commands via ex1b.c (already done)
                # Get list of processes after execution
                after_ps = subprocess.check_output(['ps', '-ef'], universal_newlines=True)
                # Find new processes that started after execution
                before_set = set(before_ps.splitlines())
                after_set = set(after_ps.splitlines())
                new_processes = after_set - before_set
                # Assuming grader is the main process, check if any new processes are from the student's program
                leftover_processes = [proc for proc in new_processes if any(c_file.replace('.c', '') in proc for c_file in expected_c_files)]
                if leftover_processes:
                    log['Issues'].append("Child processes were not properly terminated.")
                    deductions += POINTS['child_processes']
                    log['Child Processes'] = leftover_processes
                else:
                    logging.info("No leftover child processes found.")
            except Exception as e:
                logging.error(f"Failed to check child processes: {e}")
                log['Issues'].append("Failed to check for leftover child processes.")
                deductions += POINTS['child_processes']

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

    # Read input commands
    try:
        with open(os.path.join(INPUT_DIR, 'input_ex1.txt'), 'r', encoding='utf-8') as f:
            commands_to_send = f.read().strip().splitlines()
        if len(commands_to_send) < 2:
            raise ValueError("input_ex1.txt must contain at least two lines: <output_filename> <seed> and at least one command.")
        logging.info("Loaded input commands for ex1.")
    except Exception as e:
        logging.error(f"Failed to read input_ex1.txt: {e}")
        return

    # Initialize summary list
    summary = []

    # Define expected .c files for ex1
    expected_c_files_ex1 = ['ex1a.c', 'ex1b.c', 'char_in_str.c', 'pid.c', 'unique_str.c']
    extra_c_files_ex1 = []  # Add any additional .c files if necessary

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
            commands_to_send=commands_to_send,
            expected_c_files=expected_c_files_ex1,
            extra_c_files=extra_c_files_ex1
        )
        summary.append(log)
        logging.info(f"Finished processing: {submission_folder} | Final Score: {log['Final Score']}")

    # Generate JSON Summary
    generate_json_summary(summary, summary_file)

    logging.info("Grading complete.")

if __name__ == "__main__":
    main()
